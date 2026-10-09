"""Unit tests for scripts/check_brand_name.py.

The gate blocks merges on the retired identity, so both directions get
tests: a rule that silently stops matching turns the gate into a rubber stamp,
and one that silently widens starts flagging kiro-cli, the harness Warding
legitimately drives. The script's own ``--test`` mode covers the same rule
families; these tests add the git-diff scoping, the scope rules end to end,
the file-level scan, and the exit-code contract that ``--test`` cannot reach
without a repository.
"""

from __future__ import annotations

import importlib.util
import math
import os
import subprocess
import sys
import time

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_PATH = os.path.join(_REPO_ROOT, "scripts", "check_brand_name.py")


def _load():
    spec = importlib.util.spec_from_file_location("check_brand_name", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_brand_name"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()

# The retired identity, in every spelling the probes below need. Each one is
# assembled from fragments so this file carries none of them and stays clean
# under the gate it tests.
_KIRO, _CREW, _GHOST = "kiro", "crew", "ghost"
_KIRO_CAP, _CREW_CAP = _KIRO.capitalize(), _CREW.capitalize()
_NAME = _KIRO_CAP + _CREW_CAP
_NAME_SPACED = f"{_KIRO_CAP} {_CREW_CAP}"
_NAME_CLI = _KIRO + _CREW
_NAME_ENV = _NAME_CLI.upper()
_NAME_PKG = f"{_KIRO}_{_CREW}"
_NAME_HYPHEN = f"{_KIRO}-{_CREW}"
_HOME_POSIX = f"~/.{_KIRO}/{_CREW}"
_HOME_WINDOWS = f"C:\\Users\\me\\.{_KIRO}\\{_CREW}"
_HOME_ESCAPED = f"C:\\\\Users\\\\me\\\\.{_KIRO}\\\\{_CREW}"
_HOME_JOINED = f"~/.{_NAME_CLI}"
_HOST = f"{_CREW}.{_KIRO}.dev"
_BUNDLE_ID = ".".join(("com", "ama" + "zon", _KIRO, _CREW))
_ORG = f"{_KIRO}dotdev"
_SLUG = f"{_ORG}/{_NAME}"
_MASCOT = _KIRO.capitalize() + _GHOST.capitalize()


def _hits(line: str, path: str = "probe.py") -> list[str]:
    return [v.token for v in gate.scan_line(path, 1, line)]


def _kinds(line: str, path: str = "probe.py") -> list[str]:
    return [v.kind for v in gate.scan_line(path, 1, line)]


# ---------------------------------------------------------------------------
# The retired identity, in every spelling and every context
# ---------------------------------------------------------------------------


class TestProse:
    @pytest.mark.parametrize(
        "line",
        [
            f"{_NAME} keeps working while you sleep.",
            f"{_NAME_SPACED} keeps working while you sleep.",
            f"Run {_NAME_SPACED.lower()} on your own hardware.",
            f"This is {_NAME}'s own sandbox.",
            f"shipped with {_NAME}.",
            f"every {_NAME}-owned file",
            f'"about_blurb": "A companion built into {_NAME_SPACED}."',
            f"# {_NAME} needs Python >= 3.10 at runtime",
        ],
    )
    def test_prose_is_flagged(self, line: str) -> None:
        assert _kinds(line) == ["brand"], f"missed: {line}"

    @pytest.mark.parametrize(
        "token",
        [
            _NAME,
            _NAME.lower(),
            _NAME.upper(),
            _KIRO.capitalize() + _CREW,
            _KIRO + _CREW.capitalize(),
            _NAME_SPACED,
            _NAME_SPACED.lower(),
            _NAME_SPACED.upper(),
            f"{_KIRO.capitalize()}-{_CREW.capitalize()}",
            f"{_KIRO.capitalize()}_{_CREW.capitalize()}",
            f"{_KIRO}.{_CREW}",
            f"{_KIRO}+{_CREW}",
            f"{_KIRO}  {_CREW}",
            f"{_KIRO}\t{_CREW}",
            f"{_KIRO_CAP}\u00a0{_CREW_CAP}",
            f"{_KIRO_CAP}/{_CREW_CAP}",
            f"{_KIRO_CAP}\\{_CREW_CAP}",
            f"{_KIRO_CAP}\\\\{_CREW_CAP}",
            f"{_KIRO_CAP}--{_CREW_CAP}",
            f"{_KIRO}__{_CREW}",
            # Unicode joiners: a hyphen, an en dash, an em dash, a soft hyphen and
            # the zero-width characters.
            f"{_KIRO_CAP}\u2010{_CREW_CAP}",
            f"{_KIRO_CAP}\u2013{_CREW_CAP}",
            f"{_KIRO_CAP}\u2014{_CREW_CAP}",
            f"{_KIRO_CAP}\u00ad{_CREW_CAP}",
            f"{_KIRO}\u200b{_CREW}",
            f"{_KIRO}\u200d{_CREW}",
            f"{_KIRO}\u2060{_CREW}",
            # Encoded and escaped spaces.
            f"{_KIRO_CAP}%20{_CREW_CAP}",
            f"{_KIRO_CAP}&nbsp;{_CREW_CAP}",
            f"{_KIRO_CAP}\\ {_CREW_CAP}",
        ],
    )
    def test_every_case_and_separator_is_flagged(self, token: str) -> None:
        assert _hits(f"powered by {token} today") == [token]

    @pytest.mark.parametrize(
        "token",
        [
            f"{_KIRO_CAP} ?{_CREW_CAP}",
            f"{_KIRO}.?{_CREW}",
            f"{_KIRO}-?{_CREW}",
            f"{_KIRO}\\.{_CREW}",
            f"{_KIRO}\\s*{_CREW}",
            f"{_KIRO}\\s?{_CREW}",
            f"{_KIRO}[ -]?{_CREW}",
            f"{_KIRO}[-._ ]?{_CREW}",
            # A class naming the slash is a joiner like any other.
            f"{_KIRO}[/_]{_CREW}",
            f"{_KIRO}[\\\\/]{_CREW}",
            f"{_KIRO}[\\s_-]?{_CREW}",
            # Escaped joiners and regex classes after a backslash.
            f"{_KIRO}\\W?{_CREW}",
            f"{_KIRO}\\-{_CREW}",
            f"{_KIRO}\\_{_CREW}",
            f"{_KIRO}\\/{_CREW}",
            # A short group of joiners, capturing or not.
            f"{_KIRO}(?:-|_)?{_CREW}",
            f"{_KIRO}(?:\\s|-|_)?{_CREW}",
            f"{_KIRO}(-|_){_CREW}",
        ],
    )
    def test_a_regex_spelling_of_the_name_is_the_name(self, token: str) -> None:
        # A pattern written to match the retired name carries it just as well: a
        # title-stripping regex or an allowlist entry is residue like any other.
        assert _hits(f"pattern = /{token}/g") == [token]

    @pytest.mark.parametrize(
        "line",
        [
            # A sentence ending on the harness's name, then one opening on the word.
            f"The harness is {_KIRO_CAP}. {_CREW_CAP} agents then pick it up.",
            f"Pick {_KIRO}.  {_CREW_CAP} members follow.",
            f"Is it {_KIRO}? {_CREW_CAP} members decide.",
            f"{_KIRO_CAP}, {_CREW} and more",
            f"{_KIRO_CAP}; {_CREW} next",
            f"{_KIRO_CAP}! {_CREW_CAP} ahoy",
            f"{_KIRO_CAP} - {_CREW} as a spaced aside",
            f"{_KIRO_CAP} (the harness) and its {_CREW}",
        ],
    )
    def test_clause_punctuation_between_the_words_is_not_the_name(self, line: str) -> None:
        # The joiner is one bounded unit, and punctuation that ends a clause is not
        # one: the harness's name next to the generic word is not the retired name.
        assert _hits(line) == [], f"false positive: {line}"

    def test_multiple_hits_on_one_line_are_all_reported(self) -> None:
        line = f"{_NAME} talks to {_NAME_SPACED} over SSH"
        assert _hits(line) == [_NAME, _NAME_SPACED]


class TestIdentifiers:
    """No system still owns a retired spelling, so identifiers are residue too."""

    @pytest.mark.parametrize(
        "line",
        [
            f"run `{_NAME_CLI} serve` to start the gateway",
            f"from {_NAME_PKG}.config import loader",
            f"mailto:{_NAME_HYPHEN}-security-support@example.com",
            f"resolve {_NAME}Apps from the registry",
            f"SHIM = My{_NAME}Shim()",
            f'assert "X-{_NAME}-Proxy" in headers',
            f"electron-builder signs {_NAME}.exe and Update.exe",
            f"opens /Applications/{_NAME}.app",
            f"the {_NAME}-Nightly channel",
            f'home / "Library" / "Logs" / "{_NAME} Nightly"',
            f"built from ~/src/{_NAME} last night",
            f"installed to C:\\Program Files\\{_NAME}",
        ],
    )
    def test_identifier_forms_are_flagged(self, line: str) -> None:
        assert _kinds(line) == ["brand"], f"missed: {line}"

    @pytest.mark.parametrize(
        "line",
        [
            f'os.environ["{_NAME_ENV}_HOME"]',
            f"export {_NAME_ENV}_PORT=8080",
            f"{_NAME_ENV}_DISABLE_TELEMETRY=1 warding gateway",
        ],
    )
    def test_the_environment_prefix_is_flagged(self, line: str) -> None:
        assert _hits(line) == [_NAME_ENV]

    def test_code_fences_and_inline_code_do_not_exempt(self) -> None:
        # The retired identity has no legitimate home in a shell snippet either.
        assert _hits(f"clone `{_NAME}` then start it", path="doc.md") == [_NAME]
        for line in ("```bash", f"cd {_NAME}", "```"):
            assert _hits(line, path="doc.md") == ([_NAME] if _NAME in line else [])

    def test_a_url_does_not_exempt(self) -> None:
        assert _hits(f"https://example.com/d?app={_NAME}&v=2") == [_NAME]
        assert _hits(f'<a href="https://example.com/">{_NAME}</a>') == [_NAME]

    def test_there_is_no_inline_suppression_marker(self) -> None:
        assert _hits(f"correct = '{_NAME}'  # brand-ok: transcript fixture") == [_NAME]
        assert not hasattr(gate, "SUPPRESSION")


class TestDataHome:
    def test_the_posix_data_home_is_flagged(self) -> None:
        assert _kinds(f"state lives under {_HOME_POSIX}/workspace") == ["home"]

    def test_the_windows_data_home_is_flagged(self) -> None:
        assert _kinds(f"{_HOME_WINDOWS}\\gateway.sock") == ["home"]

    def test_an_escaped_windows_data_home_is_flagged(self) -> None:
        # A Windows path inside a string literal doubles its backslashes.
        assert _kinds(f'resolve_address("{_HOME_ESCAPED}\\\\gateway.sock")') == ["home"]

    def test_the_joined_data_home_is_flagged(self) -> None:
        assert _hits(f"migrated from {_HOME_JOINED}") == [_NAME_CLI]

    @pytest.mark.parametrize(
        "line",
        [
            # A cross-platform path regex, as a test or a redaction rule writes it.
            f"re.compile(r'\\.{_KIRO}[\\\\/]{_CREW}')",
            f"re.compile(r'\\.{_KIRO}[/\\\\]+{_CREW}')",
            f"re.compile(r'\\.{_KIRO}(?:/|\\\\)+{_CREW}')",
            # A JSON-escaped slash, and a regex doubled inside a string literal.
            f'{{"home": "~\\/.{_KIRO}\\/{_CREW}"}}',
            f'new RegExp("\\\\.{_KIRO}\\\\\\\\{_CREW}")',
        ],
    )
    def test_a_regex_or_escaped_spelling_of_the_data_home_is_flagged(self, line: str) -> None:
        assert _kinds(line) == ["home"], f"missed: {line}"

    def test_the_data_home_is_reported_once_not_again_as_the_name(self) -> None:
        # The path contains the two-word name; the leftmost rule claims the span.
        assert len(_hits(f"{_HOME_POSIX}/.env")) == 1

    @pytest.mark.parametrize(
        "line",
        [
            f'CREW_HOME = Path.home() / ".{_KIRO}" / "{_CREW}"',
            f'os.path.join(os.path.expanduser("~"), ".{_KIRO}", "{_CREW}")',
            f"path.join(os.homedir(), '.{_KIRO}', '{_CREW}', 'workspace')",
            f'parts = (".{_KIRO}", "{_CREW}")',
            f'staging = Path(".{_KIRO}") / "{_CREW}-auth-staging"',
            f'Path.home().joinpath(".{_KIRO}").joinpath("{_CREW}")',
            f'legacy = home + "/.{_KIRO}/" + "{_CREW}"',
            f'root = ".{_KIRO}" + "{_CREW}"',
            f'f"{{home}}/.{_KIRO}{{os.sep}}{_CREW}"',
            f"`${{home}}/.{_KIRO}${{path.sep}}{_CREW}`",
            f"Path.home() / '.{_KIRO}' / f'{_CREW}'",
        ],
    )
    def test_the_data_home_built_from_split_literals_is_flagged(self, line: str) -> None:
        # Code rarely spells the data home as one literal: it joins kiro-cli's
        # directory and the second word with a path operator, a comma or `+`, or
        # interpolates the separator. Every one of those builds the retired path.
        assert _kinds(line) == ["home"], f"missed: {line}"

    @pytest.mark.parametrize(
        "line",
        [
            'Path.home() / ".kiro" / "settings" / "cli.json"',
            'os.path.join(home, ".kiro", "agents")',
            "path.join(os.homedir(), '.kiro', 'settings', 'mcp.json')",
            'f"{home}/.kiro{os.sep}agents"',
        ],
    )
    def test_kiro_cli_paths_built_the_same_way_are_not_flagged(self, line: str) -> None:
        assert _hits(line) == [], f"false positive: {line}"


class TestRetiredLiterals:
    @pytest.mark.parametrize("sub", ["download", "updates", "apps"])
    def test_every_host_under_the_retired_domain_is_flagged(self, sub: str) -> None:
        line = f"curl -fsSL https://{sub}.{_HOST}/cli.sh | sh"
        assert _kinds(line) == ["host"]
        assert _hits(line) == [_HOST]

    def test_the_bare_retired_domain_is_flagged(self) -> None:
        assert _kinds(f"alternate domain {_HOST.upper()}") == ["host"]

    @pytest.mark.parametrize(
        "dot",
        [
            "\\.",  # regex-escaped
            "\\\\.",  # regex-escaped inside a string literal
            "[.]",  # a one-character class
        ],
    )
    def test_a_regex_spelling_of_the_host_is_flagged(self, dot: str) -> None:
        # A test that asserts a URL against a pattern carries the retired host as
        # much as the URL itself does, so reverting such a test must still fail.
        host = _HOST.replace(".", dot)
        line = f"assert.match(manualDownloadUrl('nightly'), /^https:\\/\\/download{dot}{host}\\//)"
        assert _kinds(line) == ["host"], f"missed: {line}"
        assert _hits(line) == [host]

    def test_the_bundle_id_is_flagged_once(self) -> None:
        # It contains the two-word name too; it is reported under its own rule only.
        assert _kinds(f"codesign --identifier {_BUNDLE_ID} App.app") == ["bundle"]

    def test_a_regex_spelling_of_the_bundle_id_is_flagged_once(self) -> None:
        pattern = _BUNDLE_ID.replace(".", "\\.")
        assert _kinds(f"expect(appId).toMatch(/^{pattern}$/)") == ["bundle"]

    def test_the_slug_reports_the_org_and_the_name(self) -> None:
        assert _kinds(f"https://github.com/{_SLUG}/issues") == ["org", "brand"]
        assert _kinds(f"if: github.repository == '{_SLUG}'") == ["org", "brand"]

    def test_the_org_alone_is_flagged(self) -> None:
        assert _kinds(f"ghcr.io/{_ORG}/warding:latest") == ["org"]
        assert _kinds(f"github.repository_owner == '{_ORG}'") == ["org"]
        assert _kinds(f"registries: [{{ name: '{_ORG}-labs' }}]") == ["org"]

    def test_the_org_with_any_repository_is_flagged(self) -> None:
        # A half-renamed slug keeps the retired organisation, and an owner/repo
        # pair naming any repository is flagged the same way.
        assert _kinds(f"https://github.com/{_ORG}/warding") == ["org"]
        assert _kinds(f"{{ owner: '{_ORG}', repo: 'Other' }}") == ["org"]
        assert _kinds(f"github.com/{_ORG}/{_KIRO_CAP}Apps") == ["org"]
        # The two words glued is the retired product, never kiro-cli's repository.
        assert _kinds(f"{_ORG}/{_KIRO}{_CREW}") == ["org", "brand"]
        assert _kinds(f"{{ owner: '{_ORG}', repo: '{_NAME}' }}") == ["org", "brand"]

    @pytest.mark.parametrize(
        "line",
        [
            f"# (fix requested in {_ORG}/{_KIRO_CAP}#10970)",
            f"url: 'https://github.com/{_ORG}/{_KIRO_CAP}/issues/11'",
            f"const SCOPE = 'github:github.com:{_ORG}/{_KIRO_CAP}'",
            f"JSON.stringify({{ owner: '{_ORG}', repo: '{_KIRO_CAP}' }})",
            f'OWNER, REPO = "{_ORG}", "{_KIRO_CAP}"',
            f'{{"owner": "{_ORG}", "repo": "{_KIRO_CAP}"}}',
        ],
    )
    def test_a_citation_of_the_orgs_first_word_repository_is_flagged(self, line: str) -> None:
        assert _kinds(line) == ["org"], f"missed: {line}"

    @pytest.mark.parametrize(
        "line",
        [
            f'import {{ {_MASCOT} }} from "./components/{_MASCOT}"',
            f'<{_MASCOT} pose="wave" />',
            f"the {_KIRO.capitalize()} {_GHOST} mascot",
        ],
    )
    def test_the_mascot_is_flagged(self, line: str) -> None:
        kinds = _kinds(line)
        assert kinds and set(kinds) == {"mascot"}, f"missed: {line}"

    def test_each_finding_names_its_replacement(self) -> None:
        cases = {
            f"Run {_NAME} now": "Warding",
            f"under {_HOME_POSIX}": "~/.warding",
            f"https://download.{_HOST}/": "warding.dev",
            f"id {_BUNDLE_ID}": "dev.warding.desktop",
            f"ghcr.io/{_ORG}/x": "myrmitis/warding",
            f"<{_MASCOT} />": "assets/brand/build.py",
        }
        for line, replacement in cases.items():
            (violation,) = list(gate.scan_line("probe.py", 1, line))
            assert replacement in violation.render(), line


# ---------------------------------------------------------------------------
# What stays: kiro-cli's own spellings and the generic word
# ---------------------------------------------------------------------------


class TestNotFlagged:
    @pytest.mark.parametrize(
        "line",
        [
            # kiro-cli's own home and everything under it.
            "kiro-cli reads ~/.kiro/settings/cli.json",
            "agent configs live in ~/.kiro/agents/warding.json",
            'Path.home() / ".kiro" / "settings" / "mcp.json"',
            "C:\\Users\\me\\.kiro\\settings\\cli.json",
            # The harness itself.
            "install kiro-cli, then run `kiro-cli chat`",
            "the Kiro CLI is optional",
            "agent.acp_backend = ACP_BACKEND_KIRO",
            "is_kiro_backend(backend)",
            "see https://kiro.dev/docs/cli for the harness",
            "assert re.match(r'https://kiro\\.dev/docs', url)",
            "re.compile(r'\\.kiro[\\\\/](?:settings|agents)')",
            # The generic word on its own.
            "a remote crew instance",
            "the crew_companion app and its crews",
            "STAGE_CREW_LEAF",
            "Crew members share one Issue Radar board",
            # The two words apart.
            "kiro-cli drives the agent crew",
            "kiro, then a crew",
            # Warding itself.
            "Warding routes agents and models.",
            "Run `warding gateway` on loopback.",
            "~/.warding/security_policy.json",
            "https://download.warding.dev/cli.sh",
            "dev.warding.desktop",
            "myrmitis/warding",
        ],
    )
    def test_legitimate_spellings_are_not_flagged(self, line: str) -> None:
        assert _hits(line) == [], f"false positive: {line}"


# ---------------------------------------------------------------------------
# Linearity
# ---------------------------------------------------------------------------


class TestLinearity:
    @pytest.mark.parametrize(
        "filler,glue",
        [
            (".", " "),
            ("a-", " "),
            ("x.com", " "),
            ("`", " "),
            (f"{_KIRO} ", " "),
            (f"{_KIRO}-cli ", ""),
            (f"~/.{_KIRO}/", " "),
            (f"{_KIRO}--", " "),
            (f'.{_KIRO}" / "', " "),
            (f"{_KIRO}%20", " "),
            (f"{_KIRO}\\\\", " "),
            (f"{_KIRO}[ -]", " "),
            (f"{_KIRO}[\\s_", " "),
            (f"{_KIRO}(?:-", " "),
            (f".{_KIRO}[\\\\/]", " "),
            (f"{_CREW}\\.{_KIRO}\\.x", " "),
            ("\\", " "),
        ],
    )
    def test_a_very_long_line_stays_linear(self, filler: str, glue: str) -> None:
        # A generated file can carry one enormous line, and each filler here is a
        # run of near-misses for one rule. An unbounded quantifier would re-walk
        # the run from every offset and blow the CI job's timeout on input nobody
        # can see is pathological.
        line = filler * (200_000 // len(filler)) + glue + f"{_NAME} is here"
        started = time.monotonic()
        found = _hits(line, path="big.md")
        assert time.monotonic() - started < 2.0
        assert found == [_NAME]

    def test_many_names_on_one_line_stay_linear(self) -> None:
        # The other axis: not one long line, but MANY matches on it. Any per-match
        # step that slices the line or rescans its prefix is quadratic here, and a
        # ratio assertion catches that where a wall-clock budget loose enough for a
        # loaded runner would not.
        #
        # This mirrors the script's own ``--test`` growth check and reuses its
        # budgets, so tuning one tunes both. It measures CPU time, which does not
        # advance while the thread is off-CPU: wall clock is quantised to a
        # ~15.625ms tick on Windows, and when xdist workers oversubscribe the
        # runner the LONGER scan absorbs more preemption than the shorter one,
        # which inflates the ratio systematically. Each baseline is paired with its
        # own doubled sample, the best RATIO is kept, and a baseline too small to
        # divide is not judged. Under 2x CPU oversubscription a linear scan stays
        # at most ~2x while a quadratic one never drops below ~3.9x.
        def ratio_of(base: int) -> tuple[float, float, int, int]:
            """Best (least noisy) doubled/base CPU-time ratio over several attempts."""
            best = math.inf
            best_base = 0.0
            found = (0, 0)

            def once(count: int) -> tuple[float, int]:
                line = f"!{_NAME}" * count
                began = time.process_time()
                hits = len(_hits(line, path="big.md"))
                return time.process_time() - began, hits

            for _ in range(gate._PERF_ATTEMPTS):
                base_time, base_hits = once(base)
                doubled_time, doubled_hits = once(base * 2)
                found = (base_hits, doubled_hits)
                if base_time <= 0.0:
                    continue
                candidate = doubled_time / base_time
                if candidate < best:
                    best, best_base = candidate, base_time
            return (0.0 if best is math.inf else best), best_base, found[0], found[1]

        # Grow the workload until the baseline is big enough to divide. A regressed
        # scan clears the floor at the first size, so only the fast case ever pays
        # for a larger one.
        base_count = 0
        ratio = base_time = 0.0
        base_found = doubled_found = 0
        for base_count in gate._PERF_BASE_SIZES:
            ratio, base_time, base_found, doubled_found = ratio_of(base_count)
            if base_time >= gate._PERF_MIN_BASE_SECS:
                break

        # Match counts are a correctness assertion, not a timing one -- they hold
        # whatever the clock did, so they are checked before the floor bails out.
        assert (base_found, doubled_found) == (base_count, base_count * 2)
        if base_time < gate._PERF_MIN_BASE_SECS:
            pytest.skip(
                f"baseline {base_time * 1000:.1f}ms at {base_count} names is still below "
                f"the {gate._PERF_MIN_BASE_SECS * 1000:.0f}ms measurement floor; a ratio "
                "here would be noise divided by noise. Quadratic growth at this size "
                "costs orders of magnitude more than the floor, so this cannot be hiding "
                "a regression."
            )
        assert ratio < 3.0, (
            f"doubling the input cost {ratio:.1f}x CPU time (best of {gate._PERF_ATTEMPTS}, "
            f"baseline {base_time:.3f}s at {base_count} names); linear is ~2x, so a "
            "per-match scan of the line has come back"
        )


# ---------------------------------------------------------------------------
# Scope: no exemptions, files and diffs
# ---------------------------------------------------------------------------


class TestScope:
    def test_no_path_is_exempt(self) -> None:
        assert not hasattr(gate, "exempt")
        for path in (
            "NOTICE",
            "docs/NOTICE",
            "NOTICE.md",
            "packaging/NOTICE",
            "THIRD-PARTY-NOTICES.md",
        ):
            assert gate.in_scope(path), path

    def test_text_the_old_gate_skipped_is_now_scanned(self) -> None:
        # No generated-file, lockfile or self exemption survives: the identity is
        # retired in every one of them.
        for path in (
            "scripts/check_brand_name.py",
            "test/test_brand_name_gate.py",
            "website/electron/package.json",
            "website/package-lock.json",
            "website/src/i18n/locales/de.json",
            "src/warding/data/tips_catalog.json",
            "CHANGELOG.md",
        ):
            assert gate.in_scope(path), path

    def test_bytes_that_are_not_text_stay_out_of_scope(self) -> None:
        assert not gate.in_scope("node_modules/foo/README.md")
        assert not gate.in_scope("assets/banner.png")
        assert not gate.in_scope("src/warding/_vendor/libggml-base.so.0")
        assert gate.in_scope("README.md")

    def test_the_gate_and_its_tests_carry_no_retired_spelling(self) -> None:
        # Both are scanned like any other file, so they must stay clean themselves.
        assert gate.scan_file("scripts/check_brand_name.py") == []
        assert gate.scan_file("test/test_brand_name_gate.py") == []

    def test_scan_file_restricted_to_given_lines(self, tmp_path, monkeypatch) -> None:
        # Point the scanner's root at tmp_path rather than deriving a relative path
        # from it: on Windows the temp dir and the repo sit on different drives, and
        # os.path.relpath raises across mounts.
        monkeypatch.setattr(gate, "REPO_ROOT", str(tmp_path))
        (tmp_path / "note.md").write_text(
            f"{_NAME} one\n{_NAME} two\n{_NAME} three\n", encoding="utf-8"
        )
        assert len(gate.scan_file("note.md")) == 3
        assert [v.line_no for v in gate.scan_file("note.md", {2})] == [2]

    def test_unreadable_file_is_skipped_not_fatal(self) -> None:
        assert gate.scan_file("does/not/exist.md") == []
        assert gate.read_lines("does/not/exist.md") is None

    def test_lines_are_split_the_way_git_counts_them(self, tmp_path, monkeypatch) -> None:
        # git splits on \n only. A lone \r must not start a new line here, or every
        # line number after it points at the wrong text.
        monkeypatch.setattr(gate, "REPO_ROOT", str(tmp_path))
        (tmp_path / "crlf.md").write_bytes(b"one\r\ntwo \rstill two\r\n" + _NAME.encode() + b"\r\n")
        lines = gate.read_lines("crlf.md")
        assert lines is not None and len(lines) == 4  # 3 real lines + trailing ""
        assert [v.line_no for v in gate.scan_file("crlf.md")] == [3]


@pytest.mark.xdist_group(name="subprocess_spawn")
class TestDiffScopedRun:
    """End-to-end through a throwaway repo: only ADDED lines may fail the gate."""

    @staticmethod
    def _repo(tmp_path) -> str:
        root = str(tmp_path / "repo")
        os.makedirs(root)
        run = lambda *a: subprocess.run(a, cwd=root, check=True, capture_output=True)  # noqa: E731
        run("git", "init", "-q", "-b", "main")
        run("git", "config", "user.email", "t@example.com")
        run("git", "config", "user.name", "t")
        os.makedirs(os.path.join(root, "scripts"))
        with open(_SCRIPT_PATH, encoding="utf-8") as src:
            body = src.read()
        dest = os.path.join(root, "scripts", "check_brand_name.py")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(body)
        return root

    @staticmethod
    def _head(root: str) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    @staticmethod
    def _run(root: str, base: str | None, **env_extra: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        if base:
            env["BRAND_BASE_REF"] = base
        else:
            env.pop("BRAND_BASE_REF", None)
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "check_brand_name.py")],
            cwd=root,
            env=env,
            capture_output=True,
            # The gate writes UTF-8 deliberately. `text=True` would decode with the
            # locale's preferred encoding, which is cp1252 on Windows, and a
            # non-ASCII path in a finding would come back as mojibake.
            encoding="utf-8",
            errors="replace",
        )

    def _commit(self, root: str, name: str, body: str, msg: str) -> None:
        target = os.path.join(root, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(body)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", msg], cwd=root, check=True, capture_output=True)

    def test_preexisting_residue_does_not_fail_the_diff_gate(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", f"Old line about {_NAME}.\n", "base")
        base = self._head(root)
        self._commit(root, "doc.md", f"Old line about {_NAME}.\nA clean new line.\n", "head")

        result = self._run(root, base)
        assert result.returncode == 0, result.stdout
        assert "no retired identity" in result.stdout

    def test_added_residue_fails_and_names_the_replacement(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", "Nothing to see.\n", "base")
        base = self._head(root)
        self._commit(root, "doc.md", f"Nothing to see.\nNow with {_NAME} in it.\n", "head")

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert result.stdout.startswith("::error::brand gate:")
        assert "doc.md:2" in result.stdout
        assert "Warding" in result.stdout

    @pytest.mark.parametrize(
        "line",
        [
            f"export {_NAME_ENV}_HOME=/tmp/x",
            f"state under {_HOME_POSIX}",
            f'home = Path.home() / ".{_KIRO}" / "{_CREW}"',
            f"curl https://updates.{_HOST}/feed",
            f"identifier {_BUNDLE_ID}",
            f"ghcr.io/{_ORG}/warding",
            f"<{_MASCOT} />",
        ],
    )
    def test_every_rule_family_fails_the_diff_gate(self, tmp_path, line: str) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "run.sh", "#!/bin/sh\n", "base")
        base = self._head(root)
        self._commit(root, "run.sh", f"#!/bin/sh\n{line}\n", "head")

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "run.sh:2" in result.stdout

    def test_the_root_notice_is_scanned_like_any_other_file(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "README.md", "clean\n", "base")
        base = self._head(root)
        attribution = f"This product includes {_NAME} by its original authors.\n"
        self._commit(root, "NOTICE", attribution, "attribution")

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "NOTICE:1" in result.stdout

        # A nested NOTICE is no different.
        self._commit(root, "docs/NOTICE", attribution, "nested")
        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "docs/NOTICE:1" in result.stdout

    def test_no_base_ref_reports_the_whole_tree_without_failing(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", f"Prose about {_NAME} everywhere.\n", "base")

        result = self._run(root, None)
        assert result.returncode == 0, result.stdout
        assert "::notice::" in result.stdout
        assert "doc.md:1" in result.stdout

    def test_the_whole_tree_report_includes_the_root_notice(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "NOTICE", f"{_NAME} attribution\n", "base")

        result = self._run(root, None)
        assert result.returncode == 0, result.stdout
        assert "NOTICE:1" in result.stdout

    # --- the three ways a diff-scoped gate can skip itself green -------------

    def test_a_no_diff_gitattribute_cannot_hide_a_file(self, tmp_path) -> None:
        # `-diff` makes git report only "Binary files differ" with no @@ hunks.
        # Without --text there is nothing to scan and the file passes unread.
        root = self._repo(tmp_path)
        self._commit(root, ".gitattributes", "*.md -diff\n", "base")
        base = self._head(root)
        self._commit(root, "doc.md", f"Run {_NAME} today.\n", "head")

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "doc.md:1" in result.stdout

    def test_a_non_ascii_path_cannot_hide_a_file(self, tmp_path) -> None:
        # git quotes such a path as `+++ "b/docs/\346..."`, which a `+++ b/` parser
        # misses — and then misattributes the hunks to whichever file came before.
        root = self._repo(tmp_path)
        self._commit(root, "clean.md", "nothing here\n", "base")
        base = self._head(root)
        self._commit(root, "日本語.md", f"Run {_NAME} today.\n", "head")

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "日本語.md:1" in result.stdout
        assert "clean.md" not in result.stdout

    def test_an_undecodable_changed_file_fails_closed(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "clean.md", "nothing here\n", "base")
        base = self._head(root)
        with open(os.path.join(root, "notes.txt"), "wb") as fh:
            fh.write(b"text\n\xff\xfe not utf-8\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "head"], cwd=root, check=True, capture_output=True)

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "cannot read" in result.stdout
        assert "notes.txt" in result.stdout

    def test_a_pure_deletion_hunk_contributes_nothing(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", f"keep\n{_NAME} line\nkeep\n", "base")
        base = self._head(root)
        self._commit(root, "doc.md", "keep\nkeep\n", "head")

        result = self._run(root, base)
        assert result.returncode == 0, result.stdout

    def test_a_brand_new_file_is_scanned(self, tmp_path) -> None:
        # `@@ -0,0 +1,N @@` — the shape every added file produces.
        root = self._repo(tmp_path)
        self._commit(root, "existing.md", "nothing\n", "base")
        base = self._head(root)
        self._commit(root, "fresh.md", f"line one\nRun {_NAME} here.\n", "head")

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "fresh.md:2" in result.stdout

    def test_a_base_with_no_common_ancestor_still_enforces(self, tmp_path) -> None:
        # What a shallow CI clone looks like: the base is fetched as its own tip, so
        # `merge-base` finds nothing and the base tip has to serve as the range end.
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", "clean\n", "first")
        subprocess.run(
            ["git", "checkout", "-q", "--orphan", "detached"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        self._commit(root, "doc.md", f"Now with {_NAME} in it.\n", "orphan")
        assert (
            subprocess.run(
                ["git", "merge-base", "main", "HEAD"], cwd=root, capture_output=True
            ).returncode
            != 0
        ), "precondition: the two histories must share no ancestor"

        result = self._run(root, "main")
        assert result.returncode == 1, result.stdout
        assert "doc.md:1" in result.stdout

    def test_a_translated_catalog_is_enforced(self, tmp_path) -> None:
        # Generated catalogs are shipped text; the identity is retired there too.
        root = self._repo(tmp_path)
        os.makedirs(os.path.join(root, "website/src/i18n/locales"))
        self._commit(root, "website/src/i18n/locales/de.json", "{}\n", "base")
        base = self._head(root)
        self._commit(
            root,
            "website/src/i18n/locales/de.json",
            f'{{\n  "update": "{_NAME} wird aktualisiert"\n}}\n',
            "head",
        )

        result = self._run(root, base)
        assert result.returncode == 1, result.stdout
        assert "de.json:2" in result.stdout

    def test_a_clean_verdict_survives_a_non_utf8_console(self, tmp_path) -> None:
        # The clean verdict ends in a check mark and the error line carries an em
        # dash. A cp1252 console (the Windows default) cannot encode the check mark,
        # which turned a PASS into a traceback and failed the build on a good tree.
        # PYTHONIOENCODING reproduces that on any platform.
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", "nothing here\n", "base")
        base = self._head(root)
        self._commit(root, "doc.md", "nothing here\nstill clean\n", "head")

        result = self._run(root, base, PYTHONIOENCODING="ascii")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        assert "UnicodeEncodeError" not in result.stderr
        assert "no retired identity" in result.stdout

    def test_a_non_ascii_path_is_printable_on_a_non_utf8_console(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "clean.md", "nothing here\n", "base")
        base = self._head(root)
        self._commit(root, "日本語.md", f"Run {_NAME} today.\n", "head")

        result = self._run(root, base, PYTHONIOENCODING="ascii")
        assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        assert "UnicodeEncodeError" not in result.stderr
        # The path itself may be replacement-charactered, but the finding must print.
        assert ".md:1" in result.stdout

    def test_self_test_mode_passes(self, tmp_path) -> None:
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", "clean\n", "base")
        result = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "check_brand_name.py"), "--test"],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout
        assert "self-test passed" in result.stdout

    def test_self_test_actually_judges_the_growth_ratio(self, tmp_path) -> None:
        """The repeated-names check must reach a verdict, not skip itself.

        A baseline under the measurement floor makes the check print
        ``ratio not judged`` and test nothing, so the workload grows until the
        baseline is measurable and a real ratio is always reported.
        """
        root = self._repo(tmp_path)
        self._commit(root, "doc.md", "clean\n", "base")
        result = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "check_brand_name.py"), "--test"],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout
        verdict = [ln for ln in result.stdout.splitlines() if "repeated-names" in ln]
        assert len(verdict) == 1, f"expected one repeated-names line, got {verdict!r}"
        assert (
            "ratio not judged" not in verdict[0]
        ), f"the quadratic guard skipped its own measurement: {verdict[0]!r}"
        assert "doubling cost" in verdict[0], verdict[0]


class TestExplicitPathFailsClosed:
    """A path handed to the gate directly must be read, or the run must fail."""

    @staticmethod
    def _run(*args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.pop("BRAND_BASE_REF", None)
        return subprocess.run(
            [sys.executable, _SCRIPT_PATH, *args],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_a_nonexistent_path_fails_instead_of_reporting_clean(self) -> None:
        result = self._run("definitely/not/a/file.md")
        assert result.returncode == 1, result.stdout
        assert "never checked" in result.stdout
        assert "definitely/not/a/file.md" in result.stdout
        assert "no retired identity" not in result.stdout

    def test_an_undecodable_path_fails_closed(self, tmp_path) -> None:
        blob = tmp_path / "notes.md"
        blob.write_bytes(b"\xff\xfe\x00" + _NAME.encode())
        result = self._run(str(blob))
        assert result.returncode == 1, result.stdout
        assert "never checked" in result.stdout

    def test_a_readable_clean_path_still_passes(self, tmp_path) -> None:
        doc = tmp_path / "clean.md"
        doc.write_text("Prose about Warding and kiro-cli (~/.kiro/settings).\n", encoding="utf-8")
        result = self._run(str(doc))
        assert result.returncode == 0, result.stdout
        assert "no retired identity in the files given" in result.stdout

    def test_a_readable_dirty_path_still_fails_on_the_finding(self, tmp_path) -> None:
        doc = tmp_path / "dirty.md"
        doc.write_text(f"Prose about {_NAME_SPACED}.\n", encoding="utf-8")
        result = self._run(str(doc))
        assert result.returncode == 1, result.stdout
        assert "dirty.md:1" in result.stdout
        # Failing on the finding, not on readability.
        assert "never checked" not in result.stdout

    def test_the_gate_and_its_tests_pass_their_own_scan(self) -> None:
        # Neither is exempt, so both must stay clean through the real entry point.
        result = self._run("scripts/check_brand_name.py", "test/test_brand_name_gate.py")
        assert result.returncode == 0, result.stdout

    def test_a_notice_outside_the_repository_root_is_scanned(self, tmp_path) -> None:
        notice = tmp_path / "NOTICE"
        notice.write_text(f"{_NAME} attribution\n", encoding="utf-8")
        result = self._run(str(notice))
        assert result.returncode == 1, result.stdout
        assert "NOTICE:1" in result.stdout


class TestReportDisclosesTruncation:
    """The whole-tree report must not hide the backlog it claims to report.

    The listing is path-sorted, so a silent cut shows only the alphabetically
    first paths while the report prints a large total.
    """

    def test_a_truncated_report_says_so_and_tallies_by_path(self, capsys) -> None:
        violations = [
            gate.Violation(f"{top}/f{i}.md", 1, _NAME, _NAME)
            # 'zzz' sorts last, so a silent head-slice would drop it entirely.
            for top, count in (("aaa", 40), ("zzz", 5))
            for i in range(count)
        ]
        assert gate.report(violations, enforcing=False, base=None) == 0
        out = capsys.readouterr().out

        assert "... and 5 more" in out
        # The tally must carry the paths the listing could not reach.
        assert "zzz/" in out
        assert "   40  aaa/" in out
        assert "    5  zzz/" in out
        assert "all 45 lines" in out

    def test_an_untruncated_report_adds_no_tally_or_notice(self, capsys) -> None:
        violations = [gate.Violation("a.md", 1, _NAME, _NAME)]
        assert gate.report(violations, enforcing=False, base=None) == 0
        out = capsys.readouterr().out
        assert "more" not in out
        assert "by top-level path" not in out
        assert "a.md:1" in out

    def test_the_enforcing_path_keeps_its_own_cap_and_notice(self, capsys) -> None:
        violations = [gate.Violation(f"f{i}.md", 1, _NAME, _NAME) for i in range(205)]
        assert gate.report(violations, enforcing=True, base="HEAD") == 1
        out = capsys.readouterr().out
        assert "... and 5 more" in out
        # The per-path tally is a report-path affordance; enforcement stays terse.
        assert "by top-level path" not in out

    def test_a_root_level_path_is_tallied_without_a_trailing_slash(self, capsys) -> None:
        violations = [
            gate.Violation("install.sh" if i % 2 else "docs/a.md", 1, _NAME, _NAME)
            for i in range(50)
        ]
        assert gate.report(violations, enforcing=False, base=None) == 0
        out = capsys.readouterr().out
        assert "install.sh" in out
        assert "install.sh/" not in out
        assert "docs/" in out
