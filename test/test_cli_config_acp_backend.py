"""``config set agent.acp_backend``: refuse what the loader would ignore, and
say what the next new session runs."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from warding.cli_config import _config_cmd
from warding.config import WardingConfig


def _set(value: str, *, local: bool = False) -> None:
    args = argparse.Namespace(
        config_action="set", key="agent.acp_backend", value=value, file=None, local=local
    )
    with patch("warding.cli_config.sel"):
        _config_cmd(args)


def test_set_persists_and_names_the_harness_new_sessions_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set("codex")
    out = capsys.readouterr().out
    assert WardingConfig.load().agent.acp_backend == "codex"
    # The availability suffix is host state; the selection is not.
    assert "  harness: codex (selected=codex" in out
    assert "without a gateway restart" in out


def test_set_kiro_alias_is_accepted(capsys: pytest.CaptureFixture[str]) -> None:
    from warding.acp.types import ACP_BACKEND_KIRO

    _set("kiro")
    assert WardingConfig.load().agent.acp_backend == ACP_BACKEND_KIRO
    assert "  harness: kiro-cli (selected=kiro-cli" in capsys.readouterr().out


@pytest.mark.parametrize("local", [False, True])
def test_unknown_harness_is_refused_before_writing(
    local: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    # The loader degrades an unknown value to auto (H3) with only a log line, so
    # a write would print success for a harness the gateway never runs.
    with pytest.raises(SystemExit) as exc:
        _set("bogus", local=local)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Unknown harness 'bogus'" in err
    assert WardingConfig.load().agent.acp_backend == "auto"
