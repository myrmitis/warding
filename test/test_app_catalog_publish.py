"""The published official catalog: in sync, accepted by the client, and hosted.

``site/public/catalog/official-registry.json`` is what ``apps.getjunction.dev``
serves. A stock client names no catalog origin; once an operator points
``JUNCTION_APP_CATALOG_BASE`` there and it is reachable, the store renders from
it INSTEAD of the bundled seed. So a stale or incomplete document is not
cosmetic: a built-in it omits disappears from Discover, and a seed app it omits
cannot be installed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from junction.apps import official_catalog, registry

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "build_app_catalog.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_app_catalog", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_app_catalog"] = module
    spec.loader.exec_module(module)
    return module


builder = _load()


def _published() -> dict[str, Any]:
    return json.loads(builder.OUTPUT_PATH.read_text(encoding="utf-8"))


def _manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(builder.BUILTINS_DIR.glob("*/app.json"))
    ]


class TestCommittedDocument:
    def test_matches_the_generator(self):
        # A built-in manifest edited without regenerating leaves the store showing
        # the old copy, or no row at all for a new app.
        assert builder.OUTPUT_PATH.read_text(encoding="utf-8") == builder.render(
            builder.build_document()
        ), "stale catalog; run: python3 scripts/build_app_catalog.py"

    def test_the_client_accepts_the_envelope(self):
        assert official_catalog._envelope_error(_published()) is None

    def test_lists_every_visible_builtin_and_no_hidden_one(self):
        builtins = {e["name"] for e in _published()["apps"] if e["source"] == {"type": "builtin"}}
        manifests = _manifests()
        assert builtins == {m["name"] for m in manifests if not m.get("hidden")}
        assert not builtins & {m["name"] for m in manifests if m.get("hidden")}

    def test_every_seed_app_is_a_pinned_row_the_client_can_install(self):
        seed = json.loads(builder.SEED_PATH.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in official_catalog.inventory(_published()["apps"])}
        assert set(rows) == {entry["name"] for entry in seed}
        for entry in seed:
            row = rows[entry["name"]]
            assert len(row["commit"]) == 40
            # Same repository as the seed, or `registry` keeps the unpinned seed
            # row and the pin never applies.
            assert registry._catalog_row_supersedes_seed(entry, row)

    def test_store_rows_carry_the_builtin_artwork(self, monkeypatch):
        monkeypatch.setattr(official_catalog, "load_official_catalog", lambda: _published()["apps"])
        rows = {row["name"]: row for row in official_catalog.list_catalog_rows()}
        for manifest in _manifests():
            if manifest.get("hidden"):
                continue
            row = rows[manifest["name"]]
            assert row["source"] == {"type": "builtin"}
            assert row["iconUrl"] == manifest["iconUrl"]
            assert row["heroImage"] == manifest["heroImage"]

    def test_an_older_builtin_install_is_not_offered_an_update(self, monkeypatch):
        # The store decides `updateAvailable` by comparing the row's version with
        # the installed one, and a built-in only updates with the wheel.
        monkeypatch.setattr(official_catalog, "load_official_catalog", lambda: _published()["apps"])
        rows = [r for r in official_catalog.list_catalog_rows() if r["source"]["type"] == "builtin"]
        installed = {r["name"]: {"version": "0.0.1", "origin": "builtin"} for r in rows}
        enriched = registry._enrich_with_install_status(rows, installed)
        assert enriched and not any(row["updateAvailable"] for row in enriched)


class TestHosting:
    def test_a_stock_client_names_no_catalog_origin(self, monkeypatch):
        # Publishing the document never turns the fetch on: the operator opts in.
        monkeypatch.delenv(official_catalog.CATALOG_BASE_ENV, raising=False)
        assert not official_catalog.catalog_configured()
        assert official_catalog.catalog_document_url(official_catalog.OFFICIAL_CATALOG_FILE) == ""

    def test_the_catalog_host_serves_the_committed_file(self, monkeypatch):
        # The chain an operator opts into: with the catalog base pointed at the
        # published base, the document URL's host is rewritten (never redirected --
        # the client refuses redirects) onto the directory the generator writes
        # into, under the site's `public/`.
        monkeypatch.setenv(official_catalog.CATALOG_BASE_ENV, builder.PUBLISHED_BASE)
        url = urllib.parse.urlsplit(
            official_catalog.catalog_document_url(official_catalog.OFFICIAL_CATALOG_FILE)
        )
        assert url.hostname
        config = json.loads((_REPO_ROOT / "site" / "vercel.json").read_text(encoding="utf-8"))
        assert not any(
            {"type": "host", "value": url.hostname} in r.get("has", [])
            for r in config.get("redirects", [])
        )
        [rewrite] = [
            r
            for r in config["rewrites"]
            if {"type": "host", "value": url.hostname} in r.get("has", [])
        ]
        assert rewrite["source"] == "/:path*"
        destination = rewrite["destination"].replace(":path*", url.path.lstrip("/"))
        assert _REPO_ROOT / "site" / "public" / destination.lstrip("/") == builder.OUTPUT_PATH


class TestGeneratorRefuses:
    def _seed(self, tmp_path: Path, name: str = "demo-app") -> Path:
        path = tmp_path / "app-registry.json"
        url = f"https://example.com/{name}"
        path.write_text(
            json.dumps([{"name": name, "gitUrl": url, "branch": "main"}]), encoding="utf-8"
        )
        return path

    def _pins(self, tmp_path: Path, pins: dict[str, Any]) -> Path:
        path = tmp_path / "pins.json"
        path.write_text(json.dumps(pins), encoding="utf-8")
        return path

    def test_a_seed_app_without_a_pin(self, tmp_path: Path):
        with pytest.raises(builder.CatalogError, match="unpinned: \\['demo-app'\\]"):
            builder.git_entries(self._seed(tmp_path), self._pins(tmp_path, {}))

    def test_a_branch_where_a_commit_belongs(self, tmp_path: Path):
        pins = {"demo-app": {"ref": "main", "manifest": {"version": "1.0.0"}}}
        with pytest.raises(builder.CatalogError, match="not pinned to a commit"):
            builder.git_entries(self._seed(tmp_path), self._pins(tmp_path, pins))

    def test_a_pinned_app_without_a_version(self, tmp_path: Path):
        pins = {"demo-app": {"ref": "a" * 40, "manifest": {"displayName": "Demo"}}}
        with pytest.raises(builder.CatalogError, match="has no version"):
            builder.git_entries(self._seed(tmp_path), self._pins(tmp_path, pins))

    def test_a_builtin_asset_the_catalog_host_would_have_to_serve(self, tmp_path: Path):
        app = tmp_path / "demo" / "app.json"
        app.parent.mkdir()
        app.write_text(json.dumps({"name": "demo-app", "heroImage": "hero.svg"}), encoding="utf-8")
        with pytest.raises(builder.CatalogError, match="not a client-local path"):
            builder.builtin_entries(tmp_path)

    def test_a_pinned_row_the_seed_names_is_published_with_the_seed_url(self, tmp_path: Path):
        pins = {"demo-app": {"ref": "a" * 40, "manifest": {"version": "1.2.0", "author": "x"}}}
        [entry] = builder.git_entries(self._seed(tmp_path), self._pins(tmp_path, pins))
        assert entry == {
            "name": "demo-app",
            "source": {"type": "git", "url": "https://example.com/demo-app", "ref": "a" * 40},
            "author": {"name": "x"},
            "version": "1.2.0",
        }
