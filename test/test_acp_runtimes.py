"""ACP runtime registry: auto-select and spawn argv without kiro-cli."""

from __future__ import annotations

from pathlib import Path

import pytest

from warding.acp.runtimes import (
    AUTO_PREFERENCE,
    RuntimeNotFoundError,
    builtin_specs,
    dsh_launcher_override,
    resolve_backend,
    resolve_spawn_argv,
    runtime_available,
    select_runtime,
    session_load_meta,
)
from warding.acp.types import (
    ACP_BACKEND_AUTO,
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_DSH,
    ACP_BACKEND_KIRO,
    ACP_BACKEND_OPENCODE,
    ACP_BACKENDS_SELECTABLE,
    ACP_BACKENDS_SPEC_FAMILY,
)
from warding.platform_compat import IS_WINDOWS


def _which_for(installed: dict[str, str]):
    def which(name: str) -> str | None:
        return installed.get(name)

    return which


def _kiro_binary(tmp_path: Path, *, runnable: bool) -> Path:
    """A ``WARDING_KIRO_BIN`` target that is, or is not, runnable on this host.

    Windows has no execute bit, so runnability there is the extension
    (``platform_compat.is_executable_file``) and a mode change means nothing.
    """
    if IS_WINDOWS:
        binary = tmp_path / ("kiro-cli.exe" if runnable else "kiro-cli.txt")
    else:
        binary = tmp_path / "kiro-cli"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755 if runnable else 0o644)
    return binary


class TestBuiltinSpecs:
    def test_cursor_is_cursor_agent_acp(self):
        spec = builtin_specs()[ACP_BACKEND_CURSOR]
        assert spec.argv == ("cursor-agent", "acp")
        assert spec.protocol == "spec"
        assert spec.is_spec is True

    def test_opencode_is_opencode_acp(self):
        spec = builtin_specs()[ACP_BACKEND_OPENCODE]
        assert spec.argv == ("opencode", "acp")
        assert spec.is_spec is True
        assert ACP_BACKEND_OPENCODE in ACP_BACKENDS_SPEC_FAMILY
        assert ACP_BACKEND_OPENCODE in AUTO_PREFERENCE

    def test_kiro_is_optional_and_not_spec(self):
        spec = builtin_specs()[ACP_BACKEND_KIRO]
        assert spec.argv == ("kiro-cli", "acp")
        assert spec.protocol == "kiro"
        assert spec.is_spec is False

    def test_every_auto_preference_has_a_spec(self):
        specs = builtin_specs()
        for runtime_id in AUTO_PREFERENCE:
            assert runtime_id in specs

    def test_spec_family_ids_are_selectable(self):
        assert ACP_BACKENDS_SPEC_FAMILY <= ACP_BACKENDS_SELECTABLE
        assert ACP_BACKEND_AUTO in ACP_BACKENDS_SELECTABLE
        assert ACP_BACKEND_KIRO in ACP_BACKENDS_SELECTABLE


class TestAvailability:
    def test_cursor_requires_cursor_agent(self, tmp_path: Path):
        spec = builtin_specs()[ACP_BACKEND_CURSOR]
        assert runtime_available(spec, which=_which_for({})) is False
        assert (
            runtime_available(spec, which=_which_for({"cursor-agent": "/bin/cursor-agent"})) is True
        )

    def test_dsh_is_found_on_path(self):
        spec = builtin_specs()[ACP_BACKEND_DSH]
        assert spec.argv == ("dsh-acp",)
        assert runtime_available(spec, which=_which_for({}), env={}) is False
        assert (
            runtime_available(spec, which=_which_for({"dsh-acp": "/bin/dsh-acp"}), env={}) is True
        )

    def test_dsh_override_requires_an_executable_launcher(self, tmp_path: Path):
        launcher = tmp_path / "launch-acp.sh"
        env = {"DSH_ACP_LAUNCHER": str(launcher)}
        spec = builtin_specs(env=env)[ACP_BACKEND_DSH]
        assert spec.argv == (str(launcher),)
        # The override replaces PATH lookup entirely: a PATH hit does not count.
        which = _which_for({"dsh-acp": "/bin/dsh-acp"})
        assert runtime_available(spec, which=which, env=env) is False
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        assert runtime_available(spec, which=which, env=env) is True

    def test_dsh_has_no_default_launcher_path(self):
        assert dsh_launcher_override({}) == ""

    def test_claude_available_if_claude_binary_exists(self):
        spec = builtin_specs()[ACP_BACKEND_CLAUDE]
        assert runtime_available(spec, which=_which_for({"claude": "/bin/claude"})) is True

    def test_opencode_requires_opencode(self):
        spec = builtin_specs()[ACP_BACKEND_OPENCODE]
        assert runtime_available(spec, which=_which_for({})) is False
        assert runtime_available(spec, which=_which_for({"opencode": "/bin/opencode"})) is True

    def test_codex_needs_codex_and_npx(self):
        spec = builtin_specs()[ACP_BACKEND_CODEX]
        assert runtime_available(spec, which=_which_for({"codex": "/bin/codex"})) is False
        assert (
            runtime_available(
                spec,
                which=_which_for({"codex": "/bin/codex", "npx": "/bin/npx"}),
            )
            is True
        )


class TestSelectRuntime:
    def test_auto_prefers_cursor_over_kiro(self, tmp_path: Path):
        which = _which_for(
            {
                "cursor-agent": "/bin/cursor-agent",
                "kiro-cli": "/bin/kiro-cli",
            }
        )
        spec = select_runtime(ACP_BACKEND_AUTO, which=which, env={})
        assert spec.id == ACP_BACKEND_CURSOR

    def test_auto_skips_missing_and_picks_next(self, tmp_path: Path):
        which = _which_for({"codex": "/bin/codex", "npx": "/bin/npx"})
        spec = select_runtime(ACP_BACKEND_AUTO, which=which, env={})
        assert spec.id == ACP_BACKEND_CODEX

    def test_auto_does_not_use_kiro_when_a_spec_runtime_exists(self, tmp_path: Path):
        which = _which_for(
            {
                "kimi": "/bin/kimi",
                "kiro-cli": "/bin/kiro-cli",
            }
        )
        spec = select_runtime(ACP_BACKEND_AUTO, which=which, env={})
        assert spec.id != ACP_BACKEND_KIRO
        assert spec.is_spec is True

    def test_auto_falls_back_to_kiro_only_when_nothing_else_is_installed(self, tmp_path: Path):
        which = _which_for({"kiro-cli": "/bin/kiro-cli"})
        spec = select_runtime(ACP_BACKEND_AUTO, which=which, allow_kiro=True, env={})
        assert spec.id == ACP_BACKEND_KIRO

    def test_auto_raises_when_nothing_is_installed(self, tmp_path: Path):
        with pytest.raises(RuntimeNotFoundError, match="No ACP runtime found"):
            select_runtime(ACP_BACKEND_AUTO, which=_which_for({}), allow_kiro=True, env={})

    def test_auto_finds_kiro_through_the_explicit_override(self, tmp_path: Path):
        # The spawn path resolves WARDING_KIRO_BIN before PATH, so an override
        # off PATH must count as installed, or auto finds no runtime at all.
        binary = _kiro_binary(tmp_path, runnable=True)
        env = {"WARDING_KIRO_BIN": str(binary)}
        spec = select_runtime(ACP_BACKEND_AUTO, which=_which_for({}), allow_kiro=True, env=env)
        assert spec.id == ACP_BACKEND_KIRO

    @pytest.mark.parametrize("executable", [False, None])
    def test_a_missing_or_non_executable_override_is_not_installed(
        self, tmp_path: Path, executable
    ):
        binary = (
            tmp_path / "kiro-cli"
            if executable is None
            else _kiro_binary(tmp_path, runnable=executable)
        )
        env = {"WARDING_KIRO_BIN": str(binary)}
        with pytest.raises(RuntimeNotFoundError, match="No ACP runtime found"):
            select_runtime(ACP_BACKEND_AUTO, which=_which_for({}), allow_kiro=True, env=env)

    def test_explicit_cursor_raises_if_missing(self):
        with pytest.raises(RuntimeNotFoundError, match="cursor"):
            select_runtime(ACP_BACKEND_CURSOR, which=_which_for({}))

    def test_explicit_unknown_raises(self):
        with pytest.raises(RuntimeNotFoundError, match="Unknown"):
            select_runtime("bogus", which=_which_for({}))

    def test_resolve_spawn_argv_cursor(self):
        argv = resolve_spawn_argv(
            ACP_BACKEND_CURSOR,
            which=_which_for({"cursor-agent": "/bin/cursor-agent"}),
        )
        assert argv == ["cursor-agent", "acp"]

    def test_session_load_meta_is_not_kiro_for_spec_family(self):
        assert session_load_meta(ACP_BACKEND_CURSOR, session_file="/tmp/x.json") is None
        assert session_load_meta(ACP_BACKEND_CLAUDE, session_file="/tmp/x.json") == {
            "claudeCode": {"options": {}}
        }
        assert session_load_meta(ACP_BACKEND_KIRO, session_file="/tmp/x.json") == {
            "_kiro.dev/session_file": "/tmp/x.json"
        }


class TestResolveBackend:
    def test_explicit_backends_pass_through(self, tmp_path: Path):
        assert resolve_backend(ACP_BACKEND_CODEX, which=_which_for({}), env={}) == (
            ACP_BACKEND_CODEX
        )
        assert resolve_backend(ACP_BACKEND_KIRO, which=_which_for({}), env={}) == (ACP_BACKEND_KIRO)

    def test_auto_is_the_first_installed_harness(self, tmp_path: Path):
        which = _which_for({"opencode": "/bin/opencode", "kiro-cli": "/bin/kiro-cli"})
        assert resolve_backend(ACP_BACKEND_AUTO, which=which, env={}) == (ACP_BACKEND_OPENCODE)

    def test_auto_with_nothing_installed_is_kiro(self, tmp_path: Path):
        assert resolve_backend(ACP_BACKEND_AUTO, which=_which_for({}), env={}) == (ACP_BACKEND_KIRO)


class TestAcpClientSpawnUsesRegistry:
    """AcpClient._spawn must not require kiro-cli for a spec-family backend."""

    def test_is_spec_true_for_cursor(self):
        from warding.acp.client import AcpClient

        client = AcpClient(acp_backend=ACP_BACKEND_CURSOR, work_dir="/tmp")
        assert client._is_spec is True
        assert client._is_kiro is False
        assert client._is_claude is False
