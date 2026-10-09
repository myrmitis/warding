"""Manifest contract tests for the Companion builtin app.

The manifest declares an in-process backend (routes plus lifecycle hooks) and no
separate process, so enabling the app launches nothing and cannot fail on a machine
without a particular application installed. Top-level asset fields point at brand
SVGs under ``/app-assets/desk-companion/``, served by the gateway static mount
rather than an app-relative ``ui.entry`` bundle.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from warding.apps.builtins.desk_companion import hooks as hooks_mod
from warding.apps.builtins.desk_companion.backend import routes as routes_mod
from warding.apps.discovery import discover_builtin_apps
from warding.apps.manifest import AppManifest

_BUILTIN_DIR = Path(__file__).resolve().parents[1]
_APP_JSON = _BUILTIN_DIR / "app.json"
# repo_root/src/warding/apps/builtins/desk_companion/tests/test_manifest.py
_REPO_ROOT = Path(__file__).resolve().parents[6]
_APP_ASSETS_DIR = _REPO_ROOT / "website" / "public" / "app-assets"

_ROUTE_RE = re.compile(r"^/[A-Za-z0-9][A-Za-z0-9._~-]*$")
_ASSET_FIELDS = ("iconUrl", "heroImage", "heroImageDark")
_ASSET_PREFIX = "/app-assets/desk-companion/"


def _raw() -> dict:
    return json.loads(_APP_JSON.read_text(encoding="utf-8"))


def _manifest() -> AppManifest:
    return AppManifest.from_json_file(_APP_JSON)


def test_app_json_exists() -> None:
    assert _APP_JSON.is_file(), f"missing manifest: {_APP_JSON}"


def test_manifest_validates_with_no_errors() -> None:
    errors = _manifest().validate(app_root=_BUILTIN_DIR)
    assert errors == [], f"manifest validation errors: {errors}"


def test_identity() -> None:
    m = _manifest()
    assert m.name == "desk-companion"
    assert m.version == "1.0.0"
    assert m.displayName == "Companion"
    assert m.author == "warding"


def test_discovered_as_builtin() -> None:
    names = {a["name"] for a in discover_builtin_apps()}
    assert "desk-companion" in names


def test_default_enabled_is_boolean_false() -> None:
    val = _raw().get("defaultEnabled")
    assert val is False
    assert isinstance(val, bool)


def test_exactly_one_ui_page() -> None:
    pages = _raw().get("ui", {}).get("pages", [])
    assert len(pages) == 1


def test_route_is_single_top_level_segment() -> None:
    # A nested route (more than one path segment) silently redirects to /chat,
    # so the page must live at a single top-level segment.
    route = _raw()["ui"]["pages"][0]["route"]
    assert route == "/desk-companion"
    assert _ROUTE_RE.match(route), f"route {route!r} is not a single segment"


def test_permissions_api_scopes_own_backend() -> None:
    """The backend is now IN-PROCESS, so its routes live under the gateway's own
    ``/api/apps/<name>/`` prefix rather than behind the reverse proxy at
    ``/apps/<name>/api``. This assertion changed with the architecture: the old
    path does not exist any more, and asserting it would pin a shape that
    required a second process.
    """
    api = _raw().get("permissions", {}).get("api", [])
    assert "/api/apps/desk-companion" in api
    assert "/api/apps/desk-companion/*" in api


def test_asset_urls_under_app_assets_and_files_exist() -> None:
    raw = _raw()
    missing_field = [f for f in _ASSET_FIELDS if f not in raw]
    assert not missing_field, f"manifest missing asset fields: {missing_field}"

    missing_file: list[str] = []
    for field in _ASSET_FIELDS:
        url = raw[field]
        assert isinstance(url, str) and url.startswith(_ASSET_PREFIX), (
            f"{field}={url!r} must be under {_ASSET_PREFIX}"
        )
        rel = url[len("/app-assets/"):]
        if not (_APP_ASSETS_DIR / rel).is_file():
            missing_file.append(f"{field} -> {url}")
    # NOTE: a sibling agent draws these SVGs into
    # website/public/app-assets/desk-companion/. They are present as of writing
    # (icon.svg, hero-light.svg, hero-dark.svg); this assertion fails loudly if
    # a rename/removal drops one.
    assert not missing_file, "declared asset(s) with no file on disk:\n" + "\n".join(
        missing_file
    )


def test_no_absolute_user_path_in_builtin_dir() -> None:
    # Guards the SHIPPED builtin files (manifest + package code) against a
    # hardcoded absolute home path. The tests/ dir is excluded: it is not part
    # of the app surface and legitimately contains the "/Users/" literal it
    # scans for.
    offenders: list[str] = []
    for path in _BUILTIN_DIR.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/Users/" in text:
            offenders.append(str(path.relative_to(_BUILTIN_DIR)))
    assert not offenders, f"absolute /Users/ path(s) found in: {offenders}"


def test_declares_no_separate_process_backend() -> None:
    """The inverse of the assertion this replaced, and the point of the migration.

    This manifest used to declare an ``mcpServers`` entry whose ``url`` was
    ``http://127.0.0.1:7778/mcp`` — a SEPARATE macOS app the gateway proxied to.
    That single field is what made the whole class of defects reachable: the
    ``.app_secret`` the proxy signs with, the malformed-port crash that could
    stop gateway startup, and the hole where a never-enabled app still had an
    authenticated route to its backend.

    There is no second process now, so there must be no loopback backend URL to
    resolve. Asserting the absence is what stops someone reintroducing it.
    """
    servers = _raw().get("mcpServers", {})
    for name, cfg in servers.items():
        url = cfg.get("url", "")
        assert not url, (
            f"mcpServers[{name!r}] declares url={url!r}; the backend runs "
            "in-process, so a loopback URL means a second process crept back in"
        )


def test_does_not_launch_anything_on_enable() -> None:
    """Enabling must not run a command that can fail.

    ``setup.onEnable`` used to be ``open "$HOME/Applications/Companion.app"``,
    and ``handle_app_api_proxy`` rolls an enable BACK when that script fails. On
    every machine without that app already present — which is every machine but
    the author's — the tile therefore could not be switched on at all. Nothing
    here may reintroduce a launch step: the window follows the enabled state
    instead, so there is nothing to fail and nothing to roll back.
    """
    raw = _raw()
    assert "onEnable" not in raw.get("setup", {}), (
        "setup.onEnable is what made this app impossible to enable"
    )
    assert "openCommand" not in raw, (
        "openCommand would point at a separate app that is not shipped"
    )
    platform = raw.get("platform", {})
    assert "clientInstall" not in platform, (
        "clientInstall describes installing a separate app on the user's machine"
    )
    assert platform.get("installMode") != "client", (
        "installMode 'client' means 'the user installs this themselves'"
    )


def test_declares_an_in_process_backend_that_imports() -> None:
    """The hooks and routes the gateway will call must exist and be importable.

    A typo in either dotted path is otherwise a runtime failure at enable time,
    on a code path that only runs on a machine where someone enabled the app.
    """
    backend = _raw().get("backend", {})
    assert backend.get("routes") == "backend.routes:register_routes"
    hooks = backend.get("hooks", {})
    assert hooks.get("on_startup") == "hooks:on_startup"
    assert hooks.get("on_shutdown") == "hooks:on_shutdown"

    assert callable(hooks_mod.on_startup)
    assert callable(hooks_mod.on_shutdown)
    assert callable(routes_mod.register_routes)


def test_requires_the_desktop_app_declaratively() -> None:
    """A flag the shell reads, not a shell command it runs.

    The companion needs the desktop app to have somewhere to draw its
    window, and this is how that is stated — so the dashboard can gate the tile
    instead of the enable failing on a machine with no shell.
    """
    assert _raw().get("platform", {}).get("requiresDesktopApp") is True
