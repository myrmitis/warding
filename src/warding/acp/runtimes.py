"""ACP runtime registry — spawn argv for each dockable coding agent.

Warding's harness plane treats ACP as a family of stdio JSON-RPC agents
(Cursor, Claude, Codex, DeepSeek Harness, Pi, Kimi, Goose, Grok, OpenCode,
Droid, …).
``kiro-cli`` is one selectable backend, last in auto preference, and optional.

This module imports nothing beyond the stdlib, ``warding.acp.types`` and
``warding.platform_compat``, so tests can exercise it without spawning a
gateway.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from warding import platform_compat
from warding.acp.types import (
    ACP_BACKEND_AUTO,
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_DROID,
    ACP_BACKEND_DSH,
    ACP_BACKEND_GOOSE,
    ACP_BACKEND_GROK,
    ACP_BACKEND_KIMI,
    ACP_BACKEND_KIRO,
    ACP_BACKEND_OPENCODE,
    ACP_BACKEND_PI,
    ACP_BACKENDS_SPEC_FAMILY,
)

WhichFn = Callable[[str], str | None]

# Preference when ``agent.acp_backend`` is ``auto``. kiro-cli is last and
# optional: Warding docks whichever spec-family runtime is already installed.
AUTO_PREFERENCE: tuple[str, ...] = (
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_KIMI,
    ACP_BACKEND_DSH,
    ACP_BACKEND_GOOSE,
    ACP_BACKEND_GROK,
    ACP_BACKEND_OPENCODE,
    ACP_BACKEND_PI,
    ACP_BACKEND_DROID,
    ACP_BACKEND_KIRO,
)

# The DeepSeek Harness ACP launcher is resolved from PATH as this command.
# ``DSH_ACP_LAUNCHER`` names a launcher script elsewhere and takes precedence.
DSH_LAUNCHER_COMMAND = "dsh-acp"
DSH_LAUNCHER_ENV = "DSH_ACP_LAUNCHER"


class RuntimeNotFoundError(LookupError):
    """No configured ACP runtime is installed / resolvable."""


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    """How to spawn one ACP agent over stdio."""

    id: str
    argv: tuple[str, ...]
    protocol: str  # "spec" (ACP v1 integer) or "kiro" (date-stamped)
    login_hint: str
    needs: tuple[str, ...] = ()

    @property
    def is_spec(self) -> bool:
        return self.protocol == "spec"


def dsh_launcher_override(env: Mapping[str, str] | None = None) -> str:
    """The ``DSH_ACP_LAUNCHER`` path, or ``""`` when the launcher comes from PATH."""
    environ = env if env is not None else os.environ
    return environ.get(DSH_LAUNCHER_ENV, "")


def builtin_specs(
    *,
    which: WhichFn | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, RuntimeSpec]:
    """Return spawn specs. *which* is ``shutil.which`` (injectable in tests)."""
    find = which or shutil.which
    environ = env if env is not None else os.environ
    dsh = dsh_launcher_override(environ) or DSH_LAUNCHER_COMMAND

    claude_argv: tuple[str, ...]
    claude_bin = find("claude-agent-acp")
    if claude_bin:
        claude_argv = (claude_bin,)
    else:
        claude_argv = (
            "npx",
            "-y",
            "@agentclientprotocol/claude-agent-acp@^0.60.0",
        )

    codex_argv = (
        "npx",
        "-y",
        "@agentclientprotocol/codex-acp@^1.1.5",
    )
    pi_argv = ("npx", "-y", "pi-acp@^0.0.31")

    return {
        ACP_BACKEND_CURSOR: RuntimeSpec(
            id=ACP_BACKEND_CURSOR,
            argv=("cursor-agent", "acp"),
            protocol="spec",
            login_hint="Install Cursor CLI and run `cursor-agent login`.",
            needs=("cursor-agent",),
        ),
        ACP_BACKEND_CLAUDE: RuntimeSpec(
            id=ACP_BACKEND_CLAUDE,
            argv=claude_argv,
            protocol="spec",
            login_hint="Install Claude Code (`claude`) and/or `claude-agent-acp`.",
            needs=(),  # npx fallback; availability checks claude OR adapter
        ),
        ACP_BACKEND_CODEX: RuntimeSpec(
            id=ACP_BACKEND_CODEX,
            argv=codex_argv,
            protocol="spec",
            login_hint="Install Codex CLI (`npm i -g @openai/codex`) and run `codex login`.",
            needs=("codex",),
        ),
        ACP_BACKEND_KIMI: RuntimeSpec(
            id=ACP_BACKEND_KIMI,
            argv=("kimi", "acp"),
            protocol="spec",
            login_hint="Install Kimi Code and run `kimi acp --login`.",
            needs=("kimi",),
        ),
        ACP_BACKEND_DSH: RuntimeSpec(
            id=ACP_BACKEND_DSH,
            argv=(dsh,),
            protocol="spec",
            login_hint=(
                f"Install the DeepSeek Harness so `{DSH_LAUNCHER_COMMAND}` is on PATH, "
                f"or set {DSH_LAUNCHER_ENV} to its launcher script."
            ),
            needs=(),
        ),
        ACP_BACKEND_GOOSE: RuntimeSpec(
            id=ACP_BACKEND_GOOSE,
            argv=("goose", "acp"),
            protocol="spec",
            login_hint="Install goose and run `goose acp`.",
            needs=("goose",),
        ),
        ACP_BACKEND_GROK: RuntimeSpec(
            id=ACP_BACKEND_GROK,
            argv=("grok", "agent", "stdio"),
            protocol="spec",
            login_hint="Install Grok Build (`npm i -g @xai-official/grok`) and run `grok` to sign in.",
            needs=("grok",),
        ),
        ACP_BACKEND_OPENCODE: RuntimeSpec(
            id=ACP_BACKEND_OPENCODE,
            argv=("opencode", "acp"),
            protocol="spec",
            login_hint=(
                "Install OpenCode (`npm i -g opencode-ai`) and run `opencode auth login` "
                "(OpenRouter, Anthropic, OpenAI, …)."
            ),
            needs=("opencode",),
        ),
        ACP_BACKEND_PI: RuntimeSpec(
            id=ACP_BACKEND_PI,
            argv=pi_argv,
            protocol="spec",
            login_hint="Install pi (`npm i -g @mariozechner/pi-coding-agent`) or set PI_ACP.",
            needs=(),
        ),
        ACP_BACKEND_DROID: RuntimeSpec(
            id=ACP_BACKEND_DROID,
            argv=("droid", "exec", "--output-format", "acp"),
            protocol="spec",
            login_hint="Install Factory Droid CLI (`droid`).",
            needs=("droid",),
        ),
        ACP_BACKEND_KIRO: RuntimeSpec(
            id=ACP_BACKEND_KIRO,
            argv=("kiro-cli", "acp"),
            protocol="kiro",
            login_hint="Optional. Install kiro-cli and run `kiro-cli login`.",
            needs=("kiro-cli",),
        ),
    }


def runtime_available(
    spec: RuntimeSpec,
    *,
    which: WhichFn | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """True if this host can spawn *spec* without a missing-binary surprise."""
    find = which or shutil.which
    environ = env if env is not None else os.environ

    if spec.id == ACP_BACKEND_CLAUDE:
        return bool(find("claude-agent-acp") or find("claude"))
    if spec.id == ACP_BACKEND_DSH:
        override = dsh_launcher_override(environ)
        if override:
            launcher = Path(override)
            return launcher.is_file() and os.access(launcher, os.X_OK)
        return bool(find(DSH_LAUNCHER_COMMAND))
    if spec.id == ACP_BACKEND_PI:
        return bool(environ.get("PI_ACP") or find("pi") or find("pi-acp"))
    if spec.id == ACP_BACKEND_CODEX:
        return bool(find("codex") and (find("npx") or find("codex-acp")))
    if spec.id == ACP_BACKEND_KIRO:
        # kiro-cli's spawn path tries ``WARDING_KIRO_BIN`` before ``PATH``
        # (``kiro_cli.resolve_kiro_cli``), so an explicit override counts as
        # installed here too. Otherwise ``auto`` skips a kiro-cli the operator
        # pointed at directly, and finds no runtime at all when it is the only one.
        # The runnable test is the spawn path's own: Windows has no execute bit,
        # so ``os.access(X_OK)`` there accepts any existing file.
        override = environ.get("WARDING_KIRO_BIN", "")
        if override and platform_compat.is_executable_file(override):
            return True
    return all(find(name) for name in spec.needs) if spec.needs else bool(find(spec.argv[0]))


def select_runtime(
    requested: str = ACP_BACKEND_AUTO,
    *,
    which: WhichFn | None = None,
    env: Mapping[str, str] | None = None,
    allow_kiro: bool = True,
) -> RuntimeSpec:
    """Pick a concrete runtime.

    ``auto`` walks :data:`AUTO_PREFERENCE` and returns the first available
    spec. An explicit id must be available or this raises
    :class:`RuntimeNotFoundError`. kiro-cli is skipped in auto unless no
    spec-family runtime is present *and* ``allow_kiro`` is true.
    """
    specs = builtin_specs(which=which, env=env)
    if requested and requested != ACP_BACKEND_AUTO:
        spec = specs.get(requested)
        if spec is None:
            raise RuntimeNotFoundError(
                f"Unknown ACP runtime {requested!r}. "
                f"Known: {', '.join(sorted(k for k in specs if k))}"
            )
        if not runtime_available(spec, which=which, env=env):
            raise RuntimeNotFoundError(
                f"ACP runtime {requested!r} is not installed. {spec.login_hint}"
            )
        return spec

    spec_hits: list[RuntimeSpec] = []
    kiro_hit: RuntimeSpec | None = None
    for runtime_id in AUTO_PREFERENCE:
        spec = specs[runtime_id]
        if not runtime_available(spec, which=which, env=env):
            continue
        if spec.id == ACP_BACKEND_KIRO:
            kiro_hit = spec
            continue
        spec_hits.append(spec)
    if spec_hits:
        return spec_hits[0]
    if allow_kiro and kiro_hit is not None:
        return kiro_hit
    raise RuntimeNotFoundError(
        "No ACP runtime found. Install cursor-agent, claude, codex, kimi, "
        f"goose, grok, opencode, droid, pi, or the DeepSeek Harness launcher "
        f"(`{DSH_LAUNCHER_COMMAND}` on PATH, or {DSH_LAUNCHER_ENV})."
    )


def resolve_backend(
    configured: str,
    *,
    which: WhichFn | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """The concrete backend a session for *configured* ``agent.acp_backend`` runs on.

    ``auto`` resolves the way the provider does at start (first installed
    runtime). When nothing is installed the answer is ``ACP_BACKEND_KIRO``: that
    is what an unresolvable ``auto`` has always fallen back to, and callers that
    branch on the backend (the multiplexed-runtime paths, the Kiro readiness
    gate) keep their existing behavior on such a host.
    """
    if configured == ACP_BACKEND_AUTO:
        try:
            return select_runtime(ACP_BACKEND_AUTO, which=which, env=env).id
        except RuntimeNotFoundError:
            return ACP_BACKEND_KIRO
    return configured


def resolve_spawn_argv(
    runtime_id: str,
    *,
    which: WhichFn | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Return argv for a concrete (non-auto) runtime id."""
    spec = select_runtime(runtime_id, which=which, env=env, allow_kiro=True)
    return list(spec.argv)


def is_spec_backend(runtime_id: str) -> bool:
    """True for ACP v1 / stdio agents that are not kiro-cli or KAS."""
    return runtime_id in ACP_BACKENDS_SPEC_FAMILY


def session_load_meta(runtime_id: str, *, session_file: str = "") -> dict | None:
    """``_meta`` for ``session/load``. Spec-family agents get none (H5)."""
    if runtime_id == ACP_BACKEND_CLAUDE:
        return {"claudeCode": {"options": {}}}
    if runtime_id == ACP_BACKEND_KIRO:
        return {"_kiro.dev/session_file": session_file}
    return None
