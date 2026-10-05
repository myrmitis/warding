"""Tests for the pure path-primitives leaf ``junction.config.paths``.

These pin two properties of the config-loader decoupling refactor:

1. The path primitives behave identically to their historical
   ``junction.config.loader`` definitions (back-compat).
2. ``junction.config.paths`` is a genuine leaf — importing it pulls in **no**
   ``junction`` modules (in particular not the heavy ``config.loader``), so the
   modules that only need ``config_dir()`` don't transitively load the DTOs,
   schema validation, the process-global cache, and the provider factory.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from junction.config import paths


class TestConfigDir:
    """``config_dir()`` resolves ~/.junction, honoring JUNCTION_HOME."""

    @pytest.fixture(autouse=True)
    def _reset_resolved_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # config_dir() caches the resolved data home in a module global for the
        # process lifetime; reset it so each test resolves fresh against its own
        # patched Path.home / JUNCTION_HOME rather than a value another test cached.
        monkeypatch.setattr(paths, "_resolved_home", None)

    def test_default_is_home_dotjunction(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("JUNCTION_HOME", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        result = paths.config_dir()
        assert result == tmp_path / ".junction"
        assert result.is_dir()  # created on access

    def test_junction_home_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        home = tmp_path / "custom-home"
        monkeypatch.setenv("JUNCTION_HOME", str(home))
        result = paths.config_dir()
        assert result == home.resolve()
        assert result.is_dir()

    def test_junction_home_system_dir_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # A system directory must be refused and fall back to ~/.junction.
        monkeypatch.setenv("JUNCTION_HOME", "/usr")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        result = paths.config_dir()
        assert result == tmp_path / ".junction"

    def test_only_the_junction_home_is_the_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("JUNCTION_HOME", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        (tmp_path / ".kiro").mkdir()
        assert paths.config_dir() == (tmp_path / ".junction").resolve()
        assert paths.default_home_paths() == (tmp_path / ".junction",)


class TestConfigPackageDir:
    """``config_package_dir()`` points at the installed ``junction/config/``."""

    def test_points_at_config_package_with_defaults_json(self) -> None:
        pkg = paths.config_package_dir()
        assert pkg.name == "config"
        # The bundled agent defaults ship in this directory.
        assert (pkg / "defaults.json").is_file()

    def test_is_paths_module_parent(self) -> None:
        assert paths.config_package_dir() == Path(paths.__file__).resolve().parent


class TestDefaultWorkspaceBase:
    @pytest.mark.parametrize("platform_name", ["linux", "darwin", "win32"])
    def test_uses_home_workspace_on_every_platform(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform_name: str
    ) -> None:
        monkeypatch.setattr(sys, "platform", platform_name)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert paths._default_workspace_base() == tmp_path / "workspace"


class TestSafeDirName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a/b", "a_b"),
            ("a\\b", "a_b"),
            ("a:b", "a_b"),
            ("a b", "a_b"),
            ("plain", "plain"),
            ("x/y:z w", "x_y_z_w"),
        ],
    )
    def test_sanitizes_separators(self, raw: str, expected: str) -> None:
        assert paths._safe_dir_name(raw) == expected


class TestLeafPurity:
    """The whole point of the extraction: importing the leaf is cheap.

    Importing ``junction.config.paths`` in a fresh interpreter must NOT import
    ``junction.config.loader`` (or any other ``junction`` submodule). Run in a
    subprocess so the already-warm modules in this test process don't mask a
    regression.
    """

    def test_importing_paths_pulls_no_junction_modules(self) -> None:
        code = (
            "import sys\n"
            "import junction.config.paths\n"
            "leaked = sorted(\n"
            "    m for m in sys.modules\n"
            "    if m.startswith('junction')\n"
            "    and m not in {'junction', 'junction.config', 'junction.config.paths'}\n"
            ")\n"
            "print(','.join(leaked))\n"
        )
        import os

        # Ensure junction is importable in the subprocess on local dev runs
        # where PYTHONPATH may not already include the src/ directory.
        src_dir = str(Path(__file__).resolve().parents[1] / "src")
        env = dict(os.environ)
        env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        leaked = [m for m in out.stdout.strip().split(",") if m]
        assert leaked == [], f"config.paths leaf leaked junction modules: {leaked}"


class TestBackCompatReexport:
    """All primitives remain importable from ``junction.config.loader``."""

    def test_loader_reexports_match_paths(self) -> None:
        from junction.config import loader

        for name in (
            "config_dir",
            "config_package_dir",
            "_default_workspace_base",
            "_safe_dir_name",
            "CONFIG_DIR_NAME",
            "OUTBOX_DIR_NAME",
            "_WORKSPACE_DIR_NAME",
        ):
            assert getattr(loader, name) is getattr(paths, name), name

    def test_config_package_lazy_surface(self) -> None:
        # `from junction.config import X` still resolves the public surface
        # without eagerly importing the loader at package import time.
        import junction.config as cfg

        assert cfg.config_dir is paths.config_dir
        assert cfg.JunctionConfig.__name__ == "JunctionConfig"
