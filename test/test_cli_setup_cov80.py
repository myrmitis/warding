"""``cli_setup`` — helpers run by ``junction setup`` that neither the existing
setup suites nor the CLI suites exercise.

* ``_find_electron_dir`` resolves the desktop-app sources. ``JUNCTION_PROJECT_DIR``
  must win over the walk-up, the walk-up must find a real checkout, and a
  pip-installed tree with no ``website/electron`` anywhere must return ``None``
  rather than a path that does not exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from junction.cli_setup import (
    _find_electron_dir,
    _setup_slash_command,
    _setup_whatsapp,
)


class TestSetupSlashCommand:
    """``_setup_slash_command`` writes a Slack command name into config.json.

    Every guard here exists because the value lands in a Slack app manifest: a
    name with a space or 40 characters is rejected by Slack at registration
    time, long after setup has claimed success. The function must fall back to
    the current value rather than persist something unusable.
    """

    @pytest.fixture()
    def cfg_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        target = tmp_path / "config.json"
        monkeypatch.setattr("junction.cli_setup.config_path", lambda: target)
        return target

    @staticmethod
    def _answer(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
        monkeypatch.setattr("junction.cli_setup._input_or_skip", lambda prompt: value)

    def _saved(self, cfg_file: Path) -> str:
        return json.loads(cfg_file.read_text(encoding="utf-8"))["slack"]["command"]

    def test_a_valid_name_is_saved_with_the_leading_slash_stripped(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._answer(monkeypatch, "/zibble-cmd")
        _setup_slash_command()
        assert self._saved(cfg_file) == "zibble-cmd"

    def test_an_empty_answer_keeps_the_configured_name(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file.write_text(json.dumps({"slack": {"command": "quux"}}), encoding="utf-8")
        self._answer(monkeypatch, None)
        _setup_slash_command()
        assert self._saved(cfg_file) == "quux"

    def test_an_illegal_character_falls_back_to_the_current_name(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._answer(monkeypatch, "has space")
        _setup_slash_command()
        assert self._saved(cfg_file) == "junction"
        assert "letters, numbers, hyphens" in capsys.readouterr().out

    def test_an_over_long_name_falls_back_to_the_current_name(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._answer(monkeypatch, "z" * 33)
        _setup_slash_command()
        assert self._saved(cfg_file) == "junction"
        assert "too long" in capsys.readouterr().out

    def test_an_unreadable_config_aborts_the_step_without_writing(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A corrupt config must not be silently replaced by a fresh one."""
        cfg_file.write_text("{not json", encoding="utf-8")
        self._answer(monkeypatch, "zibble")
        _setup_slash_command()
        assert cfg_file.read_text(encoding="utf-8") == "{not json"
        assert "Could not read" in capsys.readouterr().out


class TestFindElectronDir:
    def test_the_project_dir_env_var_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "checkout"
        electron = root / "website" / "electron"
        electron.mkdir(parents=True)
        monkeypatch.setenv("JUNCTION_PROJECT_DIR", str(root))

        assert _find_electron_dir() == electron

    def test_falls_back_to_walking_up_from_the_module(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no env var, a source checkout is still found from this file's location."""
        monkeypatch.delenv("JUNCTION_PROJECT_DIR", raising=False)

        found = _find_electron_dir()

        assert found is not None
        assert found.is_dir()
        assert found.parts[-2:] == ("website", "electron")

    def test_returns_none_when_no_checkout_is_reachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pip-installed tree has no desktop sources — say so, don't guess a path."""
        monkeypatch.delenv("JUNCTION_PROJECT_DIR", raising=False)
        monkeypatch.setattr(Path, "is_dir", lambda self: False)

        assert _find_electron_dir() is None

    def test_an_env_var_pointing_nowhere_is_ignored_not_returned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JUNCTION_PROJECT_DIR", str(tmp_path / "does-not-exist"))

        found = _find_electron_dir()

        # It either resolves the real checkout or gives up — never the bogus root.
        assert found != (tmp_path / "does-not-exist" / "website" / "electron")


class TestSetupWhatsApp:
    """``_setup_whatsapp``: the guided WhatsApp opt-in (`junction setup --whatsapp`).

    WhatsApp has no token to collect: it pairs as a linked device on the operator's
    own account, and pairing is a QR scan served by the RUNNING gateway. So the step
    carries the three things an operator cannot discover elsewhere: the Terms of
    Service / ban risk of automating a personal account, whether the optional wheel
    is installed, and that ENABLING the channel is a config flag separate from
    pairing it. It must also persist that flag without ever damaging a config it
    could not parse.
    """

    @pytest.fixture()
    def cfg_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        target = tmp_path / "config.json"
        monkeypatch.setattr("junction.cli_setup.config_path", lambda: target)
        monkeypatch.setattr("junction.config.paths.data_home", lambda: tmp_path / "home")
        monkeypatch.setattr("junction.whatsapp.client.neonize_available", lambda: True)
        return target

    @staticmethod
    def _answer(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
        monkeypatch.setattr("junction.cli_setup._input_or_skip", lambda prompt: value)

    def test_yes_enables_the_channel_and_keeps_the_rest_of_the_config(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file.write_text(
            json.dumps({"timezone": "Europe/London", "whatsapp": {"dm_policy": "allowlist"}}),
            encoding="utf-8",
        )
        self._answer(monkeypatch, "y")

        _setup_whatsapp()

        saved = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert saved["whatsapp"]["enabled"] is True
        assert saved["whatsapp"]["dm_policy"] == "allowlist"
        assert saved["timezone"] == "Europe/London"

    def test_declining_writes_nothing(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._answer(monkeypatch, None)  # bare Enter, or a non-interactive EOF

        _setup_whatsapp()

        assert not cfg_file.exists(), "a declined opt-in must not create a config"
        assert "Left disabled" in capsys.readouterr().out

    def test_the_terms_of_service_risk_is_stated_before_the_prompt(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Enabling this channel automates the operator's PERSONAL account, which
        can get the number banned. An opt-in that does not say so is not informed."""
        self._answer(monkeypatch, "n")

        _setup_whatsapp()

        out = capsys.readouterr().out
        assert "Terms of Service" in out
        assert "banned" in out

    def test_a_missing_extra_is_named_with_its_install_command(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("junction.whatsapp.client.neonize_available", lambda: False)
        self._answer(monkeypatch, "y")

        _setup_whatsapp()

        out = capsys.readouterr().out
        assert "junction[whatsapp]" in out
        # Still enabled: the operator can install the extra afterwards, and doctor
        # reports the gap until they do. Refusing here would strand them.
        assert json.loads(cfg_file.read_text(encoding="utf-8"))["whatsapp"]["enabled"] is True

    def test_an_unreadable_config_aborts_the_step_without_writing(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg_file.write_text("{not json", encoding="utf-8")
        self._answer(monkeypatch, "y")

        _setup_whatsapp()

        assert cfg_file.read_text(encoding="utf-8") == "{not json"
        assert "Could not read" in capsys.readouterr().out

    def test_a_non_object_whatsapp_section_is_left_alone(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg_file.write_text(json.dumps({"whatsapp": "on"}), encoding="utf-8")
        self._answer(monkeypatch, "y")

        _setup_whatsapp()

        assert json.loads(cfg_file.read_text(encoding="utf-8")) == {"whatsapp": "on"}
        assert "not an object" in capsys.readouterr().out

    def test_the_step_never_imports_neonize(
        self, cfg_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The wizard reports on the credential's path, never through it: importing
        neonize loads a ~19 MB ctypes CDLL, and setup runs on every install."""
        import builtins

        real_import = builtins.__import__

        def _guard(name, *args, **kwargs):
            if name.split(".")[0] == "neonize":
                raise AssertionError(f"setup imported {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _guard)
        self._answer(monkeypatch, "y")

        _setup_whatsapp()

        assert json.loads(cfg_file.read_text(encoding="utf-8"))["whatsapp"]["enabled"] is True
