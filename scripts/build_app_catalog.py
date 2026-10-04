#!/usr/bin/env python3
"""Build the official app catalog that the ``site/`` deployment publishes.

A stock client (``junction.apps.official_catalog``) names no catalog origin and
renders the store from the bundled seed. An operator opts in by pointing
``JUNCTION_APP_CATALOG_BASE`` at a catalog base -- :data:`PUBLISHED_BASE`, where
the ``site/`` deployment serves this document, once that host answers -- and
from then on, whenever ``official-registry.json`` is reachable there, the store
renders FROM it instead of from the seed. So the document decides what Discover
lists: a built-in the document omits is not listed, and a seed app the document
omits disappears from the store the moment the catalog comes up. This script is
what keeps both lists complete.

The document is GENERATED, never hand-edited, from two inputs:

- **Built-ins**: every non-hidden ``src/junction/apps/builtins/*/app.json``,
  as ``source: {type: "builtin"}`` rows. Their code ships in the wheel, so the
  row carries display fields only, and every asset ref is the manifest's own
  absolute path: a client-local ``/app-assets/...`` URL the gateway already
  serves, which is why this host needs none of the bytes. A built-in row
  carries no ``version``: ``registry._enrich_with_install_status`` compares
  the row's version with the installed one to decide ``updateAvailable``, so
  a version bumped on ``main`` would offer every older install an Update
  button for code only a new wheel can deliver.
- **Third-party apps**: every entry of the bundled seed
  (``src/junction/apps/app-registry.json``), as ``source: {type: "git"}`` rows
  pinned to a commit. The clone URL is the seed's, so the published row
  describes the repository the wheel already names (``registry`` refuses to
  let a catalog row replace a seed row that points elsewhere). The commit and
  the baked display copy come from ``scripts/app_catalog_pins.json``, which
  ``--refresh-pins`` rewrites by resolving each seed branch to its tip and
  reading the app's ``app.json`` at exactly that commit, so the copy and the
  pin always describe the same bytes.

The output is deterministic (sorted rows, no timestamp) so ``--check`` can
compare it byte-for-byte, and it is validated with the client's OWN reader
before it is written: a document the dashboard would refuse is never produced.

Usage::

    python scripts/build_app_catalog.py                 # write the document
    python scripts/build_app_catalog.py --check         # exit 1 if it is stale
    python scripts/build_app_catalog.py --refresh-pins  # re-pin (needs network)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from junction.apps import official_catalog
from junction.apps.manifest import app_name_error

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILTINS_DIR = REPO_ROOT / "src" / "junction" / "apps" / "builtins"
SEED_PATH = REPO_ROOT / "src" / "junction" / "apps" / "app-registry.json"
PINS_PATH = REPO_ROOT / "scripts" / "app_catalog_pins.json"
#: Under the marketing site's ``public/`` so the site build copies it; the
#: site's ``vercel.json`` rewrites the ``apps.getjunction.dev`` host onto this
#: directory, which is what puts the document under :data:`PUBLISHED_BASE`.
OUTPUT_PATH = REPO_ROOT / "site" / "public" / "catalog" / "official-registry.json"
#: The catalog base the ``site/`` deployment serves this document under. Not a
#: client default: a stock build leaves ``JUNCTION_APP_CATALOG_BASE`` empty, and
#: an operator sets it to this value once the host is live.
PUBLISHED_BASE = "https://apps.getjunction.dev/"

#: The manifest fields baked into every catalog row, and the row key each lands
#: on. ``description`` becomes ``summary`` because that is the list copy the
#: store renders (``official_catalog.list_catalog_rows`` maps it back).
#: ``version`` is not here: only a ``git`` row publishes one (see the module
#: docstring for why a built-in must not).
_BAKED_STRINGS = (
    ("displayName", "displayName"),
    ("description", "summary"),
)
#: What ``--refresh-pins`` keeps from a third-party manifest: exactly the fields
#: ``_bake`` reads, so the pins file cannot grow copy nothing publishes.
_SNAPSHOT_KEYS = ("displayName", "description", "version", "tags", "author")
#: The manifest's asset fields and the row key each lands on. A built-in's
#: values are absolute gateway paths, which ``_resolve_ref`` passes through.
_BUILTIN_REFS = (
    ("iconUrl", "iconRef"),
    ("iconUrlDark", "iconRefDark"),
    ("heroImage", "heroRef"),
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}\Z")
_GIT_TIMEOUT = 60


class CatalogError(Exception):
    """The inputs cannot produce a catalog the client would accept."""


def _display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _author(value: Any) -> dict[str, str] | None:
    """The structured author the schema carries; a bare string is a name."""
    if isinstance(value, str) and value:
        return {"name": value}
    if isinstance(value, dict) and isinstance(value.get("name"), str) and value["name"]:
        return {"name": value["name"]}
    return None


def _bake(entry: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Copy the display subset of *manifest* onto *entry*, in place."""
    for source_key, row_key in _BAKED_STRINGS:
        value = manifest.get(source_key)
        if isinstance(value, str) and value:
            entry[row_key] = value
    tags = manifest.get("tags")
    if isinstance(tags, list) and all(isinstance(t, str) for t in tags) and tags:
        entry["tags"] = list(tags)
    if author := _author(manifest.get("author")):
        entry["author"] = author


def _checked_name(name: Any, where: str) -> str:
    if not isinstance(name, str) or app_name_error(name) is not None:
        raise CatalogError(f"{where}: inadmissible app name {name!r}")
    return name


def builtin_entries(builtins_dir: Path = BUILTINS_DIR) -> list[dict[str, Any]]:
    """One ``builtin`` row per built-in the store is allowed to list.

    A ``hidden`` manifest is left out rather than published and filtered: the
    store hides it on purpose, and a row for it would be a listing the client
    has to remember to suppress.
    """
    entries: list[dict[str, Any]] = []
    for manifest_path in sorted(builtins_dir.glob("*/app.json")):
        manifest = _read_json(manifest_path)
        if manifest.get("hidden"):
            continue
        where = _display_path(manifest_path)
        entry: dict[str, Any] = {
            "name": _checked_name(manifest.get("name"), where),
            "source": {"type": "builtin"},
        }
        _bake(entry, manifest)
        for manifest_key, row_key in _BUILTIN_REFS:
            ref = manifest.get(manifest_key)
            if ref is None:
                continue
            # Only an absolute ref is usable here: a relative one resolves against
            # the catalog host, which does not serve a built-in's assets.
            if (
                not isinstance(ref, str)
                or not ref.startswith("/")
                or official_catalog._resolve_ref(ref) != ref
            ):
                raise CatalogError(f"{where}: {manifest_key} {ref!r} is not a client-local path")
            entry[row_key] = ref
        entries.append(entry)
    return entries


def _seed_rows(seed_path: Path) -> list[dict[str, Any]]:
    rows = _read_json(seed_path)
    if not isinstance(rows, list):
        raise CatalogError(f"{seed_path.name} is not a JSON list")
    return [row for row in rows if isinstance(row, dict)]


def _seed_url(row: dict[str, Any]) -> str:
    url = row.get("gitUrl") or row.get("repo")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise CatalogError(f"seed entry {row.get('name')!r} has no https clone URL")
    return url


def git_entries(seed_path: Path = SEED_PATH, pins_path: Path = PINS_PATH) -> list[dict[str, Any]]:
    """One pinned ``git`` row per seed entry, from the committed pins.

    The two files must name the same apps. A seed app without a pin would vanish
    from the store whenever the catalog is up, and a pin without a seed entry
    would publish a repository the wheel never reviewed.

    No icon or hero ref is published for these rows. An absolute ref is a
    client-local path, which for an app that is not installed yet names nothing,
    and a relative one would need this host to serve the app's bytes, which it
    does not.
    """
    seed = {_checked_name(row.get("name"), seed_path.name): row for row in _seed_rows(seed_path)}
    pins = _read_json(pins_path)
    if not isinstance(pins, dict):
        raise CatalogError(f"{pins_path.name} is not a JSON object")
    if set(pins) != set(seed):
        missing = sorted(set(seed) - set(pins))
        extra = sorted(set(pins) - set(seed))
        raise CatalogError(
            f"{pins_path.name} and {seed_path.name} disagree (unpinned: {missing}, "
            f"unseeded: {extra}); run with --refresh-pins"
        )
    entries: list[dict[str, Any]] = []
    for name in sorted(seed):
        pin = pins[name]
        commit = pin.get("ref") if isinstance(pin, dict) else None
        if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
            raise CatalogError(f"{pins_path.name}: {name!r} is not pinned to a commit")
        source: dict[str, str] = {"type": "git", "url": _seed_url(seed[name]), "ref": commit}
        subdir = seed[name].get("subdirectory")
        if subdir:
            source["subdir"] = subdir
        entry: dict[str, Any] = {"name": name, "source": source}
        manifest = pin.get("manifest")
        if not isinstance(manifest, dict):
            raise CatalogError(f"{pins_path.name}: {name!r} has no manifest snapshot")
        _bake(entry, manifest)
        version = manifest.get("version")
        if not isinstance(version, str) or not version:
            # The store owns update availability for a pinned app, and it decides
            # it from this field, so a row without one could never offer an update.
            raise CatalogError(f"{pins_path.name}: {name!r} manifest has no version")
        entry["version"] = version
        entries.append(entry)
    return entries


def validate(doc: dict[str, Any]) -> None:
    """Refuse *doc* unless the client's own reader accepts every row of it."""
    problem = official_catalog._envelope_error(doc)
    if problem is not None:
        raise CatalogError(problem)
    names = [entry["name"] for entry in doc["apps"]]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise CatalogError(f"names published twice: {duplicates}")
    git_names = {e["name"] for e in doc["apps"] if e["source"]["type"] == "git"}
    installable = {row["name"] for row in official_catalog.inventory(doc["apps"])}
    if installable != git_names:
        # `inventory_for_install` REFUSES an app the catalog names without usable
        # coordinates, so a dropped row here is an app nobody can install.
        raise CatalogError(f"rows the client cannot install: {sorted(git_names - installable)}")


def build_document(
    builtins_dir: Path = BUILTINS_DIR,
    seed_path: Path = SEED_PATH,
    pins_path: Path = PINS_PATH,
) -> dict[str, Any]:
    apps = builtin_entries(builtins_dir) + git_entries(seed_path, pins_path)
    doc = {
        "schemaVersion": official_catalog.SUPPORTED_SCHEMA_VERSION,
        "apps": sorted(apps, key=lambda entry: entry["name"]),
    }
    validate(doc)
    return doc


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        raise CatalogError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _resolve_pin(row: dict[str, Any]) -> dict[str, Any]:
    """Pin *row*'s branch tip and snapshot its manifest at that exact commit."""
    url = _seed_url(row)
    branch = row.get("branch") or "main"
    listing = _git("ls-remote", url, f"refs/heads/{branch}").split()
    if not listing or not _COMMIT_RE.match(listing[0]):
        raise CatalogError(f"{url} has no branch {branch!r}")
    commit = listing[0]
    subdir = row.get("subdirectory") or ""
    manifest_path = f"{subdir.rstrip('/')}/app.json" if subdir else "app.json"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        _git("init", "--quiet", cwd=work)
        _git("fetch", "--quiet", "--depth", "1", url, commit, cwd=work)
        manifest = json.loads(_git("show", f"FETCH_HEAD:{manifest_path}", cwd=work))
    if manifest.get("name") != row.get("name"):
        raise CatalogError(f"{url}@{commit} is app {manifest.get('name')!r}, not {row['name']!r}")
    snapshot = {key: manifest[key] for key in _SNAPSHOT_KEYS if key in manifest}
    return {"ref": commit, "manifest": snapshot}


def refresh_pins(seed_path: Path = SEED_PATH, pins_path: Path = PINS_PATH) -> None:
    rows = _seed_rows(seed_path)
    pins = {row["name"]: _resolve_pin(row) for row in sorted(rows, key=lambda r: r["name"])}
    pins_path.write_text(json.dumps(pins, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(pins)} apps -> {_display_path(pins_path)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the output is stale")
    mode.add_argument(
        "--refresh-pins",
        action="store_true",
        help="re-pin every seed app to its branch tip, then rebuild",
    )
    args = parser.parse_args(argv)
    try:
        if args.refresh_pins:
            refresh_pins()
        text = render(build_document())
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    relative = _display_path(OUTPUT_PATH)
    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.is_file() else ""
        if current != text:
            print(
                f"{relative} is stale; run: python3 scripts/build_app_catalog.py",
                file=sys.stderr,
            )
            return 1
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {relative}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
