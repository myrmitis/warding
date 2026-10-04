"""Connecting harnesses: how to install and log in to each, and whether it works.

This is what the dashboard's Agents & plans panel and ``warding route check``
show. Warding never performs a login itself and never sees a credential:
every harness keeps its own sign-in, so "connecting" means running that
harness's own login command (in the dashboard terminal or a shell) and then
probing it.

A probe starts the harness over ACP exactly as a session would (sandboxed,
through the provider factory) and runs ``initialize`` + ``session/new``. No
prompt is sent, so a probe spends no quota. The outcome is persisted so the
panel can show the last result without re-spawning anything.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from junction.acp.types import (
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_GROK,
    ACP_BACKEND_OPENCODE,
)
from junction.harness_router.lanes import backend_for_harness
from junction.harness_router.limits import (
    FAILURE_AUTH,
    FAILURE_UNAVAILABLE,
    classify_exception,
)

logger = logging.getLogger(__name__)

# ── Probe outcomes (machine codes; the dashboard translates them) ──
STATUS_CONNECTED = "connected"
STATUS_NEEDS_LOGIN = "needs_login"
STATUS_NOT_INSTALLED = "not_installed"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
STATUS_UNKNOWN = "unknown"  # never probed

# npx-launched adapters download on first use, so the first probe is slow.
PROBE_TIMEOUT_SECS = 120.0
PROBES_FILENAME = "harnesses.json"
PROBES_LOCK_FILENAME = "harnesses.lock"
PROBE_DETAIL_MAX_CHARS = 240
# Advertised models kept per probe: enough for a multi-provider catalog
# (OpenCode lists every provider it is logged into, 200+), bounded so a harness
# advertising thousands cannot bloat the record.
PROBE_MODELS_MAX = 500
# Session-key prefix for probe providers (each gets its own workspace).
PROBE_SESSION_PREFIX = "route-probe"


@dataclass(frozen=True)
class HarnessSetup:
    """Shell commands that install and sign in to one harness."""

    harness: str
    install: str
    login: str
    docs_url: str

    def to_dict(self) -> dict[str, str]:
        return {"install": self.install, "login": self.login, "docs_url": self.docs_url}


# The subscriptions most operators bring. Other registry harnesses still
# connect; they show their runtime's login hint instead of commands. Claude's
# install names the ACP adapter too: Warding drives Claude Code through
# claude-agent-acp, which is not bundled with the claude CLI.
HARNESS_SETUP: Mapping[str, HarnessSetup] = MappingProxyType(
    {
        ACP_BACKEND_CLAUDE: HarnessSetup(
            harness=ACP_BACKEND_CLAUDE,
            install="npm i -g @anthropic-ai/claude-code @agentclientprotocol/claude-agent-acp",
            login="claude auth login",
            docs_url="https://docs.anthropic.com/en/docs/claude-code",
        ),
        ACP_BACKEND_CODEX: HarnessSetup(
            harness=ACP_BACKEND_CODEX,
            install="npm i -g @openai/codex",
            login="codex login",
            docs_url="https://github.com/openai/codex",
        ),
        ACP_BACKEND_CURSOR: HarnessSetup(
            harness=ACP_BACKEND_CURSOR,
            install="curl https://cursor.com/install -fsS | bash",
            login="cursor-agent login",
            docs_url="https://cursor.com/cli",
        ),
        ACP_BACKEND_GROK: HarnessSetup(
            harness=ACP_BACKEND_GROK,
            install="npm i -g @xai-official/grok",
            login="grok login",
            docs_url="https://www.npmjs.com/package/@xai-official/grok",
        ),
        ACP_BACKEND_OPENCODE: HarnessSetup(
            harness=ACP_BACKEND_OPENCODE,
            install="npm i -g opencode-ai",
            login="opencode auth login",
            docs_url="https://opencode.ai/docs",
        ),
    }
)

# Display order for the panel: the headline subscriptions first.
FEATURED_HARNESSES: tuple[str, ...] = tuple(HARNESS_SETUP)


def setup_for(harness: str) -> HarnessSetup | None:
    return HARNESS_SETUP.get(harness)


@dataclass(frozen=True)
class AdvertisedModel:
    """One model a harness advertised at ``session/new``, in its own spelling."""

    id: str
    name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


@dataclass(frozen=True)
class ProbeResult:
    """One probe's outcome."""

    harness: str
    status: str
    detail: str = ""
    models: int = 0
    checked_at: float = 0.0
    advertised: tuple[AdvertisedModel, ...] = ()

    def connected_within(self, max_age_secs: float, *, now: float) -> bool:
        """True when this is a ``connected`` outcome no older than *max_age_secs*."""
        return self.status == STATUS_CONNECTED and 0 <= now - self.checked_at <= max_age_secs

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "models": self.models,
            "checked_at": self.checked_at,
            "advertised": [m.to_dict() for m in self.advertised],
        }

    @classmethod
    def from_dict(cls, harness: str, raw: object) -> "ProbeResult":
        if not isinstance(raw, dict):
            return cls(harness=harness, status=STATUS_UNKNOWN)
        models = raw.get("models")
        checked = raw.get("checked_at")
        return cls(
            harness=harness,
            status=str(raw.get("status") or STATUS_UNKNOWN),
            detail=str(raw.get("detail") or ""),
            models=models if isinstance(models, int) and not isinstance(models, bool) else 0,
            checked_at=float(checked) if isinstance(checked, (int, float)) else 0.0,
            advertised=parse_advertised(raw.get("advertised")),
        )


def parse_advertised(raw: object) -> tuple[AdvertisedModel, ...]:
    """Parse advertised models from a stored record or an ACP ``availableModels`` list.

    Accepts ``{"id", "name"}`` as stored here and the ``modelId`` / ``value``
    keys ``acp.client.advertised_model_ids`` reads from ACP. Anything without a
    string id is skipped rather than guessed at.
    """
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[AdvertisedModel] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id") or entry.get("modelId") or entry.get("value")
        if not isinstance(model_id, str) or not model_id.strip() or model_id in seen:
            continue
        name = entry.get("name")
        seen.add(model_id)
        out.append(AdvertisedModel(id=model_id, name=name if isinstance(name, str) else ""))
        if len(out) >= PROBE_MODELS_MAX:
            break
    return tuple(out)


def _scrub(text: str) -> str:
    try:
        from junction.security import redact

        text = redact(text)
    except Exception:
        logger.debug("probe redaction unavailable", exc_info=True)
    text = " ".join(text.split())
    if len(text) > PROBE_DETAIL_MAX_CHARS:
        text = text[: PROBE_DETAIL_MAX_CHARS - 1] + "…"
    return text


def status_for_exception(exc: BaseException) -> str:
    failure = classify_exception(exc)
    if failure == FAILURE_AUTH:
        return STATUS_NEEDS_LOGIN
    if failure == FAILURE_UNAVAILABLE:
        return STATUS_NOT_INSTALLED
    return STATUS_ERROR


class ProbeStore:
    """Last probe result per harness, in ``<data home>/routing/harnesses.json``."""

    def __init__(self, directory: Path) -> None:
        self._path = directory / PROBES_FILENAME
        self._lock_path = directory / PROBES_LOCK_FILENAME

    def load(self) -> dict[str, ProbeResult]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("harness probe record unreadable (%s); ignoring", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): ProbeResult.from_dict(str(k), v) for k, v in raw.items()}

    def save(self, result: ProbeResult) -> None:
        from junction.atomic_write import atomic_write
        from junction.platform_compat import file_lock

        self._path.parent.mkdir(parents=True, exist_ok=True)
        # All harnesses and store instances share a stable sibling lock: locking
        # the JSON inode would stop protecting it after atomic replacement.
        fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with file_lock(fd, exclusive=True):
                current = self.load()
                current[result.harness] = result
                payload = {k: v.to_dict() for k, v in sorted(current.items())}
                atomic_write(self._path, json.dumps(payload, separators=(",", ":")), mode=0o600)
        finally:
            os.close(fd)


def _models_of(provider: Any) -> tuple[AdvertisedModel, ...]:
    try:
        getter = getattr(getattr(provider, "_client", None), "available_models", None)
        raw = getter() if callable(getter) else getter
        return parse_advertised(raw)
    except Exception:
        logger.debug("probe: advertised models unavailable", exc_info=True)
        return ()


ProviderMaker = Callable[[str, str], Any]


def default_provider_maker(harness: str, model: str) -> Any:
    """A provider for *harness* built the way a session builds one (sandboxed)."""
    from junction.config import JunctionConfig
    from junction.config.loader import build_provider_factory

    factory = build_provider_factory(JunctionConfig.load())
    return factory(
        f"{PROBE_SESSION_PREFIX}:{harness}",
        agent="junction",
        model_override=model or None,
        acp_backend_override=harness,
    )


async def probe_harness(
    harness: str,
    *,
    installed: bool,
    model: str = "",
    timeout: float = PROBE_TIMEOUT_SECS,
    make_provider: ProviderMaker | None = None,
    now: Callable[[], float] = time.time,
) -> ProbeResult:
    """Start *harness* once (initialize + session/new) and report the outcome."""
    if not installed:
        return ProbeResult(harness=harness, status=STATUS_NOT_INSTALLED, checked_at=now())
    maker = make_provider or default_provider_maker
    provider = None
    try:
        provider = maker(harness, model)
        await asyncio.wait_for(provider.start(), timeout=timeout)
        advertised = _models_of(provider)
        return ProbeResult(
            harness=harness,
            status=STATUS_CONNECTED,
            models=len(advertised),
            checked_at=now(),
            advertised=advertised,
        )
    except asyncio.TimeoutError:
        return ProbeResult(harness=harness, status=STATUS_TIMEOUT, checked_at=now())
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ProbeResult(
            harness=harness,
            status=status_for_exception(exc),
            detail=_scrub(str(exc) or type(exc).__name__),
            checked_at=now(),
        )
    finally:
        if provider is not None:
            try:
                await provider.shutdown()
            except Exception:
                logger.debug("probe: provider shutdown failed", exc_info=True)
        gc.collect()


def ordered_harnesses(installed: Iterable[str], configured: Iterable[str]) -> list[str]:
    """Featured harnesses first, then any other installed or configured one."""
    seen: list[str] = list(FEATURED_HARNESSES)
    for name in [*installed, *configured]:
        if name not in seen:
            seen.append(name)
    return seen


def login_hint(harness: str) -> str:
    """The runtime registry's own hint, for a harness with no setup entry."""
    try:
        from junction.acp.runtimes import builtin_specs

        spec = builtin_specs().get(backend_for_harness(harness))
        return spec.login_hint if spec is not None else ""
    except Exception:
        return ""
