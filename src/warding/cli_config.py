"""CLI config subcommand — get, set, edit configuration values."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

from warding import beacon
from warding.config import WardingConfig
from warding.config.loader import (
    ConfigReadError,
    _subtract_overlay,
    config_local_path,
    config_path,
    update_config_locked,
)
from warding.hooks import safe_read_file
from warding.sel import sel

_MISSING = object()

#: The harness setting. A running gateway adopts a new value for its next NEW
#: session, so its confirmation says what that session will run.
_ACP_BACKEND_KEY = "agent.acp_backend"


def _config_cmd(args: argparse.Namespace) -> None:
    """Get or set config values."""
    action = getattr(args, "config_action", None)
    if action == "get":

        cfg = WardingConfig.load()
        d = cfg.to_dict()
        key = getattr(args, "key", None)
        sel().log_api_access(
            caller="cli",
            operation="config_get",
            outcome="allowed",
            source="cli",
            resources=key or "*",
        )
        if not key:
            print(json.dumps(d, indent=2))
            return
        val = _dict_get(d, key)
        if val is _MISSING:
            print(f"❌ Unknown key: {key}", file=sys.stderr)
            sys.exit(1)
        if isinstance(val, (dict, list)):
            print(json.dumps(val, indent=2))
        else:
            print(val)
    elif action == "set":

        file_path = getattr(args, "file", None)
        if file_path:
            fp = Path(file_path).expanduser().resolve()

            try:
                data = json.loads(safe_read_file(str(fp)))
            except PermissionError as e:
                print(f"❌ {e}", file=sys.stderr)
                sys.exit(1)
            except (json.JSONDecodeError, OSError) as e:
                print(f"❌ Invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)
            if not isinstance(data, dict):
                # A JSON array or scalar parses fine but is not a config. Refusing
                # here keeps the file untouched; writing it through would leave a
                # config.json that every reader rejects.
                print(
                    f"❌ Not a config object: {fp} holds a JSON "
                    f"{type(data).__name__}, expected an object",
                    file=sys.stderr,
                )
                sys.exit(1)
            update_config_locked(config_path(), mutate=lambda _: data, on_corrupt="reset")
            sel().log_api_access(
                caller="cli",
                operation="config_set_file",
                outcome="allowed",
                source="cli",
                resources=str(fp),
            )
            print(f"✅ Config loaded from {file_path}")
        else:
            key = args.key
            value = args.value
            use_local = getattr(args, "local", False)
            if not key or value is None:
                print("Usage: warding config set <key> <value>", file=sys.stderr)
                print("       warding config set --local <key> <value>", file=sys.stderr)
                print("       warding config set --file <path.json>", file=sys.stderr)
                sys.exit(1)
            parsed = _parse_value(value)
            # Fourth write path to telemetry.beacon_enabled, after the dashboard
            # PATCH and `telemetry enable`. Gated here too, and BEFORE the
            # local/base split so it covers both: `--local` writes the overlay,
            # which takes precedence over the base file, so leaving it ungated
            # would make the generic setter the one way to store `true` on a
            # pinned host — the same false-promise-on-a-privacy-control failure
            # the 403 exists to prevent. Only the enable direction is refused
            # (tightest-wins), matching the other two chokepoints.
            if key == "telemetry.beacon_enabled" and parsed is True:
                # Audited for the same reason as the other enforcement calls, with
                # its own tool name so the trail says which control refused.
                if beacon.is_governance_pinned_off(audit_tool="config_set_cli"):
                    print(
                        "❌ The anonymous beacon is pinned OFF by your "
                        "administrator's security policy (capabilities.telemetry).",
                        file=sys.stderr,
                    )
                    print(
                        "   Not writing config — the setting would have no effect.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            # Same shape for the tailnet origin derivation, and placed here for the
            # same reason: BEFORE the local/base split, so `--local` (whose overlay
            # takes precedence over the base file) cannot become the one way to
            # store `true` on a pinned host. Only the enable direction is refused
            # (tightest-wins), matching the PATCH 403 and the startup gate.
            if (
                key in ("dashboard.tailscale.enabled", "dashboard.tailscale.trust_identity")
                and parsed is True
            ):
                from warding.dashboard import tailnet

                if tailnet.is_governance_pinned_off(audit_tool="config_set_cli_tailnet"):
                    print(
                        "❌ Tailnet dashboard access is pinned OFF by your "
                        "administrator's security policy "
                        "(capabilities.tailnet_origin).",
                        file=sys.stderr,
                    )
                    print(
                        "   Not writing config — the setting would have no effect.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            # Refused here, before the local/base split, for the same reason as
            # the gates above: an unknown harness is not an error at load time,
            # it silently degrades to ``auto`` (H3), so writing one would print
            # success for a setting the gateway then ignores.
            if key == _ACP_BACKEND_KEY:
                _refuse_unknown_harness(parsed)
            if use_local:
                top_key = key.split(".")[0]
                _known_sections = {f.name for f in dataclasses.fields(WardingConfig)}
                if top_key not in _known_sections:
                    print(
                        f"⚠️  Warning: '{top_key}' is not a recognized config section",
                        file=sys.stderr,
                    )
                p = config_local_path()

                # NOTE: unlike the automatic/background config writers (which now
                # fail closed via read_config_for_update), this interactive path
                # deliberately overwrites a corrupt overlay — the user typed an
                # explicit `config set --local` and sees the result on stdout.
                # Pinned by test_config_overlay.py::TestCliConfigSetLocal.
                #
                # on_corrupt="reset" handles the corrupt case inside the same
                # lock hold: the mutate callback receives {} and writes the
                # single key from scratch. No second critical section needed.
                def _mutate_local_overlay(_existing: dict) -> dict:
                    _dict_set_create(_existing, key, parsed)
                    return _existing

                update_config_locked(
                    p, mutate=_mutate_local_overlay, stamp_meta=False, on_corrupt="reset"
                )

                sel().log_api_access(
                    caller="cli",
                    operation="config_set_local",
                    outcome="allowed",
                    source="cli",
                    resources=f"{key}={json.dumps(parsed)}",
                )
                print(f"✅ {key} = {json.dumps(parsed)} (saved to config.local.json)")
                if key == _ACP_BACKEND_KEY:
                    _print_harness_effect()
            else:
                # Validate the key exists before taking the lock.
                cfg = WardingConfig.load()
                d = cfg.to_dict()
                if not _dict_set(d, key, parsed):
                    print(f"❌ Unknown key: {key}", file=sys.stderr)
                    sys.exit(1)

                def _mutate_base(existing: dict) -> dict:
                    # Apply the set on the freshly-locked raw data.
                    # Key was already validated above; use _dict_set_create so
                    # sections that were never written (still at defaults) get
                    # their intermediate keys created.
                    _dict_set_create(existing, key, parsed)
                    lp = config_local_path()
                    if lp.is_file():
                        try:
                            raw_local = json.loads(lp.read_text(encoding="utf-8"))
                            if isinstance(raw_local, dict):
                                return _subtract_overlay(existing, raw_local)
                        except (json.JSONDecodeError, OSError):
                            pass
                    return existing

                try:
                    update_config_locked(config_path(), mutate=_mutate_base)
                except ConfigReadError as e:
                    print(
                        f"❌ Cannot set key in a corrupt config.json: {e}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                sel().log_api_access(
                    caller="cli",
                    operation="config_set",
                    outcome="allowed",
                    source="cli",
                    resources=f"{key}={json.dumps(parsed)}",
                )
                print(f"✅ {key} = {json.dumps(parsed)}")
                if key == _ACP_BACKEND_KEY:
                    _print_harness_effect()
    elif action == "edit":

        p = config_path()
        if not p.exists():
            cfg = WardingConfig()
            cfg.save()
            print(f"Created default config: {p}")
        sel().log_api_access(
            caller="cli",
            operation="config_edit",
            outcome="allowed",
            source="cli",
            resources=str(p),
        )
        editor = os.environ.get("EDITOR", "vi")
        os.execvp(editor, [editor, str(p)])
    else:
        print("Usage: warding config {get,set,edit}", file=sys.stderr)
        sys.exit(1)


def _refuse_unknown_harness(parsed: object) -> None:
    """Exit before writing a harness the loader would replace with ``auto``."""
    from warding.config.loader import resolve_acp_backend_override

    try:
        resolve_acp_backend_override(parsed if isinstance(parsed, str) else str(parsed))
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        print("   Not writing config — the gateway would ignore it and run auto.", file=sys.stderr)
        sys.exit(1)


def _print_harness_effect() -> None:
    """Say what the next new session runs, in the planes screen's own words.

    Reads the merged config back rather than echoing the typed value, so an
    overlay in config.local.json that outranks the write shows up here.
    """
    from warding.planes import format_harness_line, harness_snapshot

    try:
        line = format_harness_line(harness_snapshot())
    except Exception:
        return
    print(line)
    print(
        "   New sessions start on it without a gateway restart. Open chats and the "
        "background session keep the harness they started on until they end or the "
        "gateway restarts."
    )


def _dict_get(d: dict, key: str) -> object:
    """Get a value from a nested dict using dot-separated key."""
    parts = key.split(".")
    cur: object = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return _MISSING
        cur = cur[p]
    return cur


def _dict_set(d: dict, key: str, value: object) -> bool:
    """Set a value in a nested dict using dot-separated key. Returns False if parent missing."""
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return False
        cur = cur[p]
    if not isinstance(cur, dict):
        return False
    if parts[-1] not in cur:
        return False
    cur[parts[-1]] = value
    return True


def _dict_set_create(d: dict, key: str, value: object) -> None:
    """Set a value in a nested dict, creating intermediate dicts as needed."""
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def _parse_value(raw: str) -> object:
    """Parse a CLI value string into the appropriate Python type."""
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        return json.loads(raw)
    except ValueError:
        pass
    return raw
