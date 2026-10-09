"""The self-protection deny rules recognise every console-script spelling of the CLI.

``warding`` is the CLI (``pyproject.toml`` ``[project.scripts]``) and the Python package
carries the same name, so an agent can reach every self-protected verb through the console
script, ``python -m warding`` or an inline import. These tests pin that the name is denied
everywhere the CLI is recognised as a PROGRAM or an IMPORT, that the benign mentions stay
allowed, and that words merely ending in the name (``forwarding``) never match.

Guarded literals: like ``test_denied_commands_security.py``, the words the rules match on
are assembled at runtime so this file can be read and grepped by an agent shell without
tripping the rules under test. The program names themselves come from the module's own
spelling tuple, so a console script added there is exercised here with no edit.

Asserted through ``is_denied`` and the hooks gate, the real enforcement paths, not against
``rule.pattern``: every rule here is a UNION of its regex and an argv-structural floor, and
a test of the pattern alone would pass on a floor that had stopped running.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from warding import security
from warding.hooks import TOOL_DENY, HookManager, HooksConfig
from warding.security import BUILTIN_DENIED_RULES, compute_effective_denied, is_denied

_REPO_ROOT = Path(__file__).resolve().parents[1]

_K = "k" + "ill"
_PK = "p" + _K
_KA = _K + "all"
_TOK = "to" + "ken"
_WARD = "ward" + "ing"

_PROGRAMS = security._SELF_PROGRAM_SPELLINGS

_MINT = "credential-exfil-" + _WARD + "-" + _TOK
_MINT_ARGV = _MINT + "-argv"
_KILL = "self-protection-" + _K
_KILL_INTERP = _KILL + "-interpreter"
_RESTART = "self-protection-restart"
_UPDATE = "self-protection-update"
_CLOUD = "self-protection-cloud"
_CRON_ADOPT = "self-protection-cron-adopt"
_GATEWAY_RESTART = "self-protection-gateway-restart"
# Every rule that recognises the CLI as a PROGRAM.
_PROGRAM_RULES = (
    _MINT,
    _MINT_ARGV,
    _KILL,
    _KILL_INTERP,
    _RESTART,
    _UPDATE,
    _CLOUD,
    _CRON_ADOPT,
    _GATEWAY_RESTART,
)

_RULES = {r.id: r for r in BUILTIN_DENIED_RULES}
_BY_PATTERN = {r.pattern: r.id for r in BUILTIN_DENIED_RULES}

# Subcommand rules, keyed by the CLI words that trigger them.
_SUBCOMMANDS = {
    ("restart",): _RESTART,
    ("update",): _UPDATE,
    ("gateway", "restart"): _GATEWAY_RESTART,
    ("cloud", "destroy"): _CLOUD,
}
_CLOUD_LIFECYCLE = ("destroy", "stop", "start", "launch", "connect", "tunnel", "login", "logout")


def _expand(template: str, prog: str) -> str:
    """Fill a command template: ``<p>`` the program, ``<b>`` its bracket-idiom spelling,
    ``<t>`` the mint verb and ``<pk>`` / ``<ka>`` / ``<k>`` the kill verbs."""
    return (
        template.replace("<p>", prog)
        .replace("<b>", f"[{prog[0]}]{prog[1:]}")
        .replace("<t>", _TOK)
        .replace("<pk>", _PK)
        .replace("<ka>", _KA)
        .replace("<k>", _K)
    )


def _denied_by(cmd: str) -> "str | None":
    """The id of the rule that denied *cmd* through the whole gate, or ``None``."""
    verdict = is_denied(cmd)
    if verdict is None:
        return None
    first = verdict.splitlines()[0].removeprefix(security.DENY_REASON_PREFIX)
    return _BY_PATTERN.get(first, f"<unmapped:{verdict}>")


def _denied_by_rule(cmd: str, rule_id: str) -> "str | None":
    """``_denied_by`` with ONLY *rule_id* in the effective set.

    A ``python -c`` payload that names the IMPORT name is refused by the credential-mint
    floor before any interpreter rule is consulted, so the PRECISION of an interpreter
    rule is isolated here, exactly as an operator opt-out of the mint rule would.
    """
    verdict = is_denied(cmd, denied_regexes=[_RULES[rule_id].pattern])
    if verdict is None:
        return None
    first = verdict.splitlines()[0].removeprefix(security.DENY_REASON_PREFIX)
    return _BY_PATTERN.get(first, f"<unmapped:{verdict}>")


def _name_dressings(prog: str) -> "dict[str, str]":
    """Spellings of the program NAME that the shell resolves back to *prog*."""
    mid = len(prog) // 2
    return {
        "bare": prog,
        "double-quoted": f'"{prog}"',
        "single-quoted": f"'{prog}'",
        "bracket-first": f"[{prog[0]}]{prog[1:]}",
        "bracket-mid": f"{prog[:mid]}[{prog[mid]}]{prog[mid + 1 :]}",
        "glob-one-char": f"{prog[:mid]}?{prog[mid + 1 :]}",
        "glob-run": f"{prog[0]}*{prog[-1]}",
        "empty-double-quotes": f'{prog[:mid]}""{prog[mid:]}',
        "empty-single-quotes": f"{prog[:mid]}''{prog[mid:]}",
        "empty-substitution": f"{prog[:mid]}$(){prog[mid:]}",
        "parameter-default": f"{prog[:mid]}${{x:-{prog[mid:]}}}",
        "backslash": f"{prog[:mid]}\\{prog[mid:]}",
        "ansi-c": f"$'{prog}'",
        "absolute-path": f"/usr/local/bin/{prog}",
        "home-path": f"~/.local/bin/{prog}",
        "relative-venv-path": f"./.venv/bin/{prog}",
        "exe-suffix": f"{prog}.exe",
    }


def _invocations(prog: str, words: "tuple[str, ...]") -> "list[str]":
    """Shell spellings that all reach the CLI as ``<prog> [flag] <words...>``."""
    rest = " ".join(words)
    first = words[0]
    tail = (" " + " ".join(words[1:])) if len(words) > 1 else ""
    return [
        f"{prog} {rest}",
        f"{prog} -v {rest}",
        f"{prog} -vv {rest}",
        f"{prog} --verbose {rest}",
        f"{prog} --no-jail {rest}",
        f"{prog} -v --no-jail {rest}",
        f"{prog} -\\v {rest}",
        f"{prog} \\{first}{tail}",
        f"{prog} -\\\nv {rest}",
        f"{prog} \\\n{first}{tail}",
        f"{prog} " + " ".join(f'"{w}"' for w in words),
        f"{prog} " + " ".join(f"'{w}'" for w in words),
        f'{prog} "-v" {rest}',
        f"{prog} '-v' " + " ".join(f"'{w}'" for w in words),
        f"{prog} $'-v' {rest}",
        f"{prog} $'\\x2d\\x76' {rest}",
        f"{prog} 2>/tmp/x {rest}",
        f"{prog} > /tmp/x {rest}",
        f"{prog} 2>&1 {rest}",
        f"{prog} {rest} 2>/tmp/log",
        f"sudo {prog} {rest}",
        f'bash -c "{prog} {rest}"',
        f"sh -c '{prog} {rest}'",
        f"/usr/local/bin/{prog} {rest}",
        f"~/.local/bin/{prog} {rest}",
        f"[{prog[0]}]{prog[1:]} {rest}",
        f"X={prog}; $X {rest}",
        f"alias x={prog}; x {rest}",
    ]


class TestProgramNamesTrackTheConsoleScripts:
    def test_the_floor_protects_exactly_the_installed_console_scripts(self):
        text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        section = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
        declared = {
            line.split("=", 1)[0].strip()
            for line in section.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
        assert set(_PROGRAMS) == declared
        assert _WARD in _PROGRAMS

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_a_console_script_is_recognised_as_a_whole_program_name(self, prog):
        for spelled in (
            prog,
            f"{prog}.exe",
            f"/usr/local/bin/{prog}",
            f"~/.local/bin/{prog}",
            f"./.venv/bin/{prog}",
            f'"{prog}"',
            f"{prog[:3]}?{prog[4:]}",
            f"[{prog[0]}]{prog[1:]}",
        ):
            assert security._is_self_program(spelled), spelled
        for other in (f"x{prog}", f"{prog}-wt-x", f"{prog}_notes", f"{prog}s", "forwarding"):
            assert not security._is_self_program(other), other

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_the_name_is_a_protected_name_for_the_kill_and_hint_gates(self, prog):
        assert security._SELF_NAME_RE.search(f"-f {prog}")
        assert not security._SELF_NAME_RE.search(f"-f {prog}s")
        assert security._self_floor_can_fire(f"{prog} {_TOK}")

    def test_the_hint_gate_still_skips_a_word_that_merely_ends_in_the_name(self):
        for plain in ("ls forwarding", "echo awarding rewarding", "cd forwarding-docs"):
            assert not security._self_floor_can_fire(plain), plain


class TestCatalogNamesEverySpelling:
    def test_the_walk_covers_every_rule_that_names_the_cli(self):
        """A new rule that spells the program name must join ``_PROGRAM_RULES``.

        The data-home path rule names the DIRECTORY (``~/.warding``), not the program.
        """
        naming = {
            r.id
            for r in BUILTIN_DENIED_RULES
            if re.search(r"\\b" + _WARD, r.pattern.lower())
            and not r.id.startswith("sensitive-file-read-")
        }
        assert naming == set(_PROGRAM_RULES)

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize("rule_id", _PROGRAM_RULES)
    def test_each_rule_and_its_description_name_each_spelling(self, rule_id, prog):
        rule = _RULES[rule_id]
        assert prog in rule.pattern, f"{rule_id}: pattern does not name {prog!r}"
        assert prog in rule.description, f"{rule_id}: description does not name {prog!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize("rule_id", (_MINT_ARGV, _KILL_INTERP))
    def test_interpreter_rules_cover_the_bracket_idiom(self, rule_id, prog):
        assert f"\\[{prog[0]}\\]{prog[1:]}" in _RULES[rule_id].pattern

    def test_warding_is_word_anchored_in_every_rule(self):
        """``warding`` ends other words (``forwarding``); no rule may match inside one.

        Every literal ``warding`` in a pattern sits directly behind a ``\\b`` (or behind a
        ``\\b`` that opens the alternation it belongs to).
        """
        for rule_id in _PROGRAM_RULES:
            pattern = _RULES[rule_id].pattern
            assert _WARD in pattern, rule_id
            for match in re.finditer(_WARD, pattern):
                before = pattern[: match.start()]
                assert before.endswith("\\b") or before.endswith(
                    "\\b(?:"
                ), f"{rule_id}: unanchored {_WARD!r} at {match.start()}"


class TestMintDeniedForEverySpelling:
    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            "<p> <t>",
            "<p> <t> --port 5476",
            "~/.local/bin/<p> <t> --port 5476",
            "/usr/local/bin/<p> <t>",
            "./.venv/bin/<p> <t>",
            '<p> "<t>"',
            "<p> '<t>'",
            "<p> -v --no-jail <t>",
            "<p> >/tmp/out <t>",
            "<p> 2>&1 <t>",
            "<p> pod <t> wt",
            "<b> <t>",
            "echo ok; <p> <t>",
            "true && <p> <t>",
            "<p> <t> | tee /tmp/x",
            'bash -c "<p> <t>"',
            "sh -c '<p> <t>'",
            "eval '<p> <t>'",
            "env FOO=1 <p> <t>",
            "WARDING_HOME=/tmp/h <p> <t>",
            "sudo <p> <t>",
            "nohup <p> <t>",
            "timeout 5 <p> <t>",
            "exec <p> <t>",
            "command <p> <t>",
            "ssh remote-host <p> <t>",
            "X=<p>; $X <t>",
            "alias x=<p>; x <t>",
            'f(){ <p> "$@"; }; f <t>',
            "echo <t> | xargs <p>",
            "cat <(<p> <t>)",
            "echo $(<p> <t>)",
            "<p> $(echo <t>)",
            "printf '<p> <t>' | sh",
        ],
    )
    def test_shell_forms(self, template, prog):
        cmd = _expand(template, prog)
        assert _denied_by(cmd) == _MINT, f"mint not denied: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize("label", sorted(_name_dressings(_PROGRAMS[0])))
    def test_every_dressing_of_the_name(self, label, prog):
        cmd = f"{_name_dressings(prog)[label]} {_TOK}"
        assert _denied_by(cmd) == _MINT, f"mint not denied under {label}: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            "python -c \"import subprocess; subprocess.run(['<p>','<t>'])\"",
            "python3 -c \"import subprocess; subprocess.run(['<p>', '<t>'])\"",
            'node -e \'require("child_process").execFileSync("<p>",["<t>"])\'',
            "python -c \"import os; os.execvp('<p>', ['<p>', '<t>'])\"",
            'perl -e \'system("<p>","<t>")\'',
            'ruby -e \'system "<p>", "<t>"\'',
            "python -c \"subprocess.run(['<p>','--no-jail','<t>'])\"",
            "python -c \"subprocess.run(['<p>'] + ['<t>'])\"",
            "python -c 'os.system(\"<p> <t>\")'",
            "python -c 'os.popen(\"<p> <t>\")'",
            'node -e \'require("child_process").execSync("<p> <t>")\'',
            "php -r 'shell_exec(\"<p> <t>\");'",
            "ruby -e 'system(\"<p> <t>\")'",
            "python -c 'os.system(\"<b> <t>\")'",
        ],
    )
    def test_interpreter_payloads(self, template, prog):
        cmd = _expand(template, prog)
        assert _denied_by_rule(cmd, _MINT_ARGV) == _MINT_ARGV, f"argv rule missed: {cmd!r}"
        assert is_denied(cmd) is not None, f"whole gate missed: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_a_long_gap_inside_the_quoted_string_is_still_a_mint(self, prog):
        # The gap between name and verb inside one quoted string is unbounded.
        cmd = f"python -c 'os.system(\"{prog}{' ' * 90}{_TOK}\")'"
        assert _denied_by_rule(cmd, _MINT_ARGV) == _MINT_ARGV

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_either_half_of_the_union_alone_is_enough(self, prog, monkeypatch):
        """The regex half catches a plain mint on raw text, and the floor catches the
        redirect-between-name-and-verb form the regex deliberately cannot."""
        pattern = _RULES[_MINT].pattern
        assert re.search(pattern, f"{prog} {_TOK}", re.IGNORECASE)
        assert security._is_credential_mint(f"{prog} {_TOK}")
        redirected = f"{prog} >/tmp/out {_TOK}"
        assert not re.search(pattern, redirected, re.IGNORECASE)
        assert security._is_credential_mint(redirected)

        # A tokenizer failure must not turn the floor's silence into an allow.
        def _boom(_cmd):
            raise ValueError("simulated tokenizer failure")

        monkeypatch.setattr(security, "normalize_shell_command", _boom)
        assert _denied_by(f"{prog} {_TOK}") == _MINT

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_the_retained_pattern_is_a_subset_of_the_floor_predicate(self, prog):
        rx = re.compile(_RULES[_MINT].pattern, re.IGNORECASE)
        for cmd in (
            f"{prog} {_TOK}",
            f"{prog} pod {_TOK} wt",
            f"./bin/{prog} {_TOK}",
            f"/usr/local/bin/{prog} {_TOK}",
            f"{prog} -v --no-jail {_TOK}",
            f"x; {prog} {_TOK}",
            f"$({prog} {_TOK})",
        ):
            if rx.search(cmd.lower()):
                assert security._is_credential_mint(cmd.lower()), cmd


class TestSubcommandsDeniedForEverySpelling:
    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize("words", sorted(_SUBCOMMANDS))
    def test_every_shell_dressing(self, words, prog):
        rule_id = _SUBCOMMANDS[words]
        for cmd in _invocations(prog, words):
            assert _denied_by(cmd) == rule_id, f"{rule_id} not denied: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize("words", sorted(_SUBCOMMANDS))
    @pytest.mark.parametrize("label", sorted(_name_dressings(_PROGRAMS[0])))
    def test_every_dressing_of_the_name(self, label, words, prog):
        cmd = f"{_name_dressings(prog)[label]} {' '.join(words)}"
        assert _denied_by(cmd) == _SUBCOMMANDS[words], f"not denied under {label}: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize("sub", _CLOUD_LIFECYCLE)
    def test_every_cloud_lifecycle_verb(self, sub, prog):
        assert _denied_by(f"{prog} cloud {sub}") == _CLOUD
        assert _denied_by(f"{prog} -v cloud {sub}") == _CLOUD

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            "<p> cron adopt job-1",
            "<p> -v cron adopt job-1",
            "<p> --no-jail cron adopt job-1",
            "<p> cron --json adopt job-1",
            "<p> 2>&1 cron adopt job-1",
            "/usr/local/bin/<p> cron adopt job-1",
            "sudo <p> cron adopt job-1",
            "bash -c '<p> cron adopt job-1'",
            "echo ok; <p> cron adopt job-1",
        ],
    )
    def test_cron_adopt(self, template, prog):
        cmd = _expand(template, prog)
        assert _denied_by(cmd) == _CRON_ADOPT, f"cron adopt not denied: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_both_halves_of_the_subcommand_union_name_the_spelling(self, prog):
        for words, rule_id in _SUBCOMMANDS.items():
            cmd = f"{prog} -v {' '.join(words)}"
            assert re.search(_RULES[rule_id].pattern, cmd, re.IGNORECASE), cmd
        assert security._is_self_restart(f"{prog} -\\v restart")
        assert security._is_self_update(f"{prog} \\update")
        assert security._is_self_gateway_restart(f"{prog} -\\v gateway restart")
        assert security._is_self_cloud_destructive(f"{prog} -\\v cloud destroy")


class TestKillDeniedForEverySpelling:
    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            "<pk> -f <p>",
            "<pk> <p>",
            "<ka> <p>",
            "sudo <ka> -9 <p>",
            "<pk> -9 -f '<p> gateway'",
            "<pk> -f /usr/local/bin/<p>",
            "<ka> -9 <p> > /dev/null",
            "<k> -9 $(pgrep <p>)",
            "<k> $(pgrep -f '<p> gateway')",
            "<k> $(pidof <p>)",
            "<k> $(cat /var/run/<p>.pid)",
            "<k> `pgrep <p>`",
            "<pk> -f 'x|<p>'",
            "<pk> -f '[;]*<p>'",
            '<pk> -f "[;]*<p>"',
            "<pk> -f '#<p>'",
            "<pk> -f '><p>'",
            "<pk> -f '<b>'",
            "<ka> '<b>'",
            'bash -c "<pk> -f <p>"',
            "sh -c '<ka> <p>'",
            'bash -c "<k> $(pgrep -f <p>)"',
            "$(which <pk>) -f <p>",
            "/usr/bin/<pk> -f <p>",
            "echo <p>; <pk> -f <p>",
            "env -S '<pk> -f <p>'",
            "echo <p> | xargs <pk> -f",
            "P=$(pgrep <p>); <k> $P",
        ],
    )
    def test_shell_forms(self, template, prog):
        cmd = _expand(template, prog)
        assert _denied_by(cmd) == _KILL, f"kill not denied: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "label",
        [
            "bare",
            "bracket-first",
            "bracket-mid",
            "empty-substitution",
            "parameter-default",
            "absolute-path",
        ],
    )
    def test_dressings_of_the_target(self, label, prog):
        target = _name_dressings(prog)[label]
        for cmd in (f"{_PK} -f {target}", f"{_KA} {target}", f"{_K} $(pgrep -f {target})"):
            assert _denied_by(cmd) == _KILL, f"kill not denied under {label}: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            "python -c 'import os; os.system(\"<pk> -f <p>\")'",
            'node -e \'require("child_process").execSync("<pk> -f <p>")\'',
            "php -r 'shell_exec(\"<ka> <p>\");'",
            "python -c \"subprocess.run(['<pk>','-f','<p>'])\"",
            "python -c \"subprocess.run(['<ka>','<p>'])\"",
            'node -e \'spawnSync("<pk>",["-f","<p>"])\'',
            "python -c 'os.kill(pid_from(\"<b> gateway\"), 9)'",
            "python -c 'os.killpg(pgid_of(\"<p>\"), 15)'",
            "node -e 'process.kill(pidOf(\"<p>\"), 9)'",
            "python -c 'os.system(\"<pk> -f <b>\")'",
            "python -c \"subprocess.run(['<pk>','-f','<b>'])\"",
        ],
    )
    def test_interpreter_payloads(self, template, prog):
        cmd = _expand(template, prog)
        assert _denied_by_rule(cmd, _KILL_INTERP) == _KILL_INTERP, f"rule missed: {cmd!r}"
        assert is_denied(cmd) is not None, f"whole gate missed: {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_concatenated_literals_inside_a_sink(self, prog):
        cmd = f"python -c \"import os; os.system('p'+'{_K} -f {prog}')\""
        assert _denied_by(cmd) == _KILL_INTERP

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_either_half_of_the_union_alone_is_enough(self, prog, monkeypatch):
        pattern = _RULES[_KILL].pattern
        assert re.search(pattern, f"{_PK} -f {prog}", re.IGNORECASE)
        assert security._is_self_kill(f"{_PK} -f {prog}")
        quoted = f"{_PK} -f '[;]*{prog}'"
        assert not re.search(pattern, quoted, re.IGNORECASE)
        assert security._is_self_kill(quoted)

        def _boom(_cmd):
            raise ValueError("simulated tokenizer failure")

        monkeypatch.setattr(security, "normalize_shell_command", _boom)
        assert _denied_by(f"{_PK} -f {prog}") == _KILL

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_the_retained_pattern_is_a_subset_of_the_floor_predicate(self, prog):
        rx = re.compile(_RULES[_KILL].pattern, re.IGNORECASE)
        for cmd in (
            f"{_PK} -f {prog}",
            f"{_KA} {prog}",
            f"sudo {_KA} -9 {prog}",
            f"{_PK} -f /usr/local/bin/{prog}",
            f"{_K} $(pgrep -f {prog})",
            f"{_K} $(pidof {prog})",
            f"{_K} `pgrep {prog}`",
        ):
            if rx.search(cmd.lower()):
                assert security._is_self_kill(cmd.lower()), cmd


class TestBenignMentionsStayAllowed:
    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            # The name (and the verb) as another program's DATA.
            "echo <p> <t>",
            "echo 'the <p> <t> command mints a credential'",
            "printf '%s' <p> <t>",
            "cat notes.md | grep <p> <t>",
            "git commit -m 'note: <p> <t> rule'",
            "echo <pk> <p>",
            "echo 'run <pk> <p> to stop it'",
            "echo pkill-not-run; echo <p>",
            # The name inside a path, a file name or an option.
            "ls <p>",
            "cd <p>-docs",
            "cd /work/<p>-wt-x && pytest test/test_token_auth.py",
            "git log --grep <p>",
            "grep -r <p> src/",
            "cat <p>.log",
            "tail -f /var/log/<p>.log",
            "pytest test/test_<p>_notes.py",
            "<k> 8123 && cp /tmp/<p>.json ~/",
            "<pk> other; echo <p>",
            # The CLI itself, doing anything that is not a self-protected verb.
            "<p> doctor",
            "<p> up",
            "<p> status",
            "<p> gateway",
            "<p> --version",
            "<p> -v",
            "<p> --no-jail doctor",
            "<p> -vv cloud status",
            "<p> chat -m hi",
            "<p> cron list",
            "<p> cron list | grep adopt",
            "<p> route status",
            "<p> doctor | grep <t>",
            # A lifecycle word AFTER an unrelated subcommand is not a lifecycle command.
            "<p> doctor restart",
            "<p> gateway status restart",
            "<p> cloud status destroy",
            # A regex literal or prose naming both words, not an interpreter spawn.
            "node -e '/.*<p>.*<t>/.test(cmd)'",
            "jq -r '.<p> , .<t>' cfg.json",
            "node -e 'console.log(\"<p> docs mention <t>\")'",
            "echo '<p> docs mention <t>' | tee notes.txt",
        ],
    )
    def test_allowed(self, template, prog):
        cmd = _expand(template, prog)
        assert _denied_by(cmd) is None, f"false positive on {cmd!r}"

    @pytest.mark.parametrize("prog", _PROGRAMS)
    def test_the_floor_is_not_over_broad(self, prog):
        assert not security._is_self_restart(f"{prog} -v status")
        assert not security._is_self_restart(f"echo {prog} restart")
        assert not security._is_self_restart(f"grep restart /var/log/{prog}.log")
        assert not security._is_self_cloud_destructive(f"{prog} cloud status")
        assert not security._is_self_cloud_destructive(f"{prog} -vv cloud status")
        assert not security._is_self_restart(f"{prog} gateway restart")
        assert not security._is_credential_mint(f"{prog} doctor | grep {_TOK}")
        assert not security._is_credential_mint(f"cd /work/{prog}-wt-x && pytest test_{_TOK}.py")
        assert not security._is_self_kill(f"{_K} 8123 && cp /tmp/{prog}.json ~/")

    def test_the_rule_does_not_fire_on_its_own_pattern_text(self):
        """Quoting a rule that names both spellings must not trip it."""
        for rule_id in (_MINT, _KILL, _RESTART):
            pattern = _RULES[rule_id].pattern
            for cmd in (f'grep -n "{pattern}" notes.txt', f"echo {pattern!r} >> notes.txt"):
                assert _denied_by(cmd) is None, f"{rule_id} fires on its own text: {cmd!r}"


class TestWardingIsNotMatchedInsideOtherWords:
    """``warding`` is the tail of ordinary words, so a rule must not read them as the CLI."""

    @pytest.mark.parametrize("word", ["forwarding", "awarding", "rewarding", "porforwarding"])
    @pytest.mark.parametrize(
        "template",
        [
            "<w> <t>",
            "./<w> <t>",
            "/usr/bin/<w> <t>",
            "echo x; <w> <t>",
            "<w> restart",
            "<w> update",
            "<w> -v restart",
            "<w> gateway restart",
            "<w> cloud destroy",
            "<w> cron adopt job-1",
            "<pk> -f <w>",
            "<pk> <w>",
            "<ka> <w>",
            "<k> $(pgrep -f <w>)",
            "<k> $(pidof <w>)",
            "git commit -m 'port <w> update'",
            "git commit -m 'fix <w> restart handling'",
            "systemctl restart <w>",
            "python -c \"subprocess.run(['<w>','<t>'])\"",
            "python -c \"os.system('<w> <t>')\"",
            "python -c \"import os; os.system('<pk> -f <w>')\"",
            "python -c \"subprocess.run(['<pk>','-f','<w>'])\"",
            "python -c 'os.kill(pid_from(\"<w>\"), 9)'",
        ],
    )
    def test_allowed(self, template, word):
        cmd = (
            template.replace("<w>", word)
            .replace("<t>", _TOK)
            .replace("<pk>", _PK)
            .replace("<ka>", _KA)
            .replace("<k>", _K)
        )
        assert _denied_by(cmd) is None, f"false positive on {cmd!r}"


class TestInlineProgramsNamingEitherSpelling:
    """An inline interpreter program can spawn the console script or build the verb, so the
    gate is the name together with a way to execute it: a ``-c`` payload that names either
    spelling and uses a spawn primitive is refused whatever verb it passes, however the
    primitive was imported."""

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "verb", ["restart", "update", "stop", "destroy", "launch", "adopt", _TOK]
    )
    def test_an_argv_list_spawn_is_denied(self, prog, verb):
        cmd = f"python3 -c \"import subprocess; subprocess.run(['{prog}','{verb}'])\""
        effective = compute_effective_denied(BUILTIN_DENIED_RULES, (), False, (), ())
        assert is_denied(cmd, denied_regexes=effective) is not None, cmd
        gate = HookManager(HooksConfig()).on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert gate.action == TOOL_DENY, cmd

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "payload",
        [
            "from os import posix_spawnp,environ; posix_spawnp('{p}',['{p}','restart'],environ)",
            "from os import posix_spawn,environ; posix_spawn('/x/{p}',['{p}','update'],environ)",
            "from os import system; system('{p} restart')",
            "from os import execvp; execvp('{p}',['{p}','restart'])",
            "from os import execv as e; e('/x/{p}',['{p}','stop'])",
            "import os; os.spawnvp(os.P_WAIT,'{p}',['{p}','restart'])",
            "from os import spawnlp,P_WAIT; spawnlp(P_WAIT,'{p}','{p}','restart')",
            "from pty import spawn; spawn(['{p}','restart'])",
            "from subprocess import run; run(['{p}','restart'])",
            "from subprocess import Popen as P; P(['{p}','update'])",
            "from asyncio import create_subprocess_exec as c; c('{p}','restart')",
            "import pexpect; pexpect.spawn('{p} restart')",
            "from sh import ls; import sh; sh.Command('{p}')('restart')",
        ],
    )
    def test_a_directly_imported_spawn_primitive_is_denied(self, prog, payload):
        cmd = 'python3 -c "' + payload.format(p=prog) + '"'
        gate = HookManager(HooksConfig()).on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert gate.action == TOOL_DENY, cmd

    def test_an_inline_program_that_names_the_package_is_refused(self):
        """``warding`` is also the import name, so an inline program that merely mentions it
        is refused; a word that only ends in it (``forwarding``) is inert."""
        cmd = "python3 -c \"print('warding')\""
        gate = HookManager(HooksConfig()).on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert gate.action == TOOL_DENY, cmd
        cmd = "python3 -c \"print('forwarding')\""
        gate = HookManager(HooksConfig()).on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert gate.action != TOOL_DENY, cmd

    @pytest.mark.parametrize(
        "cmd",
        [
            'python3 -c "print(1)"',
            "python3 -c \"import json; print(json.dumps({'a': 1}))\"",
            "python3 -c \"print('forwarding')\"",
            "python3 -c \"print('awarding')\"",
        ],
    )
    def test_ordinary_inline_programs_stay_allowed(self, cmd):
        gate = HookManager(HooksConfig()).on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert gate.action != TOOL_DENY, cmd


class TestImportNameIsThePackage:
    """The package carries the CLI's name, so an import of it reaches the same verbs."""

    @pytest.mark.parametrize(
        "cmd",
        [
            f"python -m {_WARD} {_TOK}",
            f"python3 -X dev -m {_WARD} {_TOK}",
            f"python -m{_WARD} {_TOK}",
            f"python -c 'import {_WARD}.cli; {_WARD}.cli.main()' {_TOK}",
            f"python -c \"from {_WARD}.cli import main; main(['{_TOK}'])\"",
            f'python -c "import {_WARD}.cli as c; c.main()"',
        ],
    )
    def test_the_package_name_is_an_import_of_the_cli(self, cmd):
        assert _denied_by(cmd) == _MINT, f"not denied: {cmd!r}"

    @pytest.mark.parametrize(
        "cmd",
        [
            f"python -m {_WARD} doctor",
            f"python3 -X dev -m {_WARD} status",
        ],
    )
    def test_a_module_run_that_names_no_protected_verb_is_allowed(self, cmd):
        # Nothing here names the mint verb, so the module run alone must not deny it.
        assert _denied_by(cmd) is None, f"denied without a protected verb: {cmd!r}"

    @pytest.mark.parametrize(
        "cmd",
        [
            f'python -c "import {_WARD}.cli"',
            f"python -c 'import {_WARD}; print(1)'",
            f"python - <<'PY'\nimport {_WARD}\nPY",
        ],
    )
    def test_an_inline_program_importing_the_package_is_refused(self, cmd):
        # An inline import can call any verb, so the import is what the floor refuses.
        assert _denied_by(cmd) is not None, f"inline import allowed: {cmd!r}"

    def test_the_import_predicates_name_the_package(self):
        assert security._SELF_MODULE_SPELLINGS == (_WARD,)
        assert security._SELF_IMPORT_RE.search(_WARD)
        assert not security._SELF_IMPORT_RE.search("forwarding")
        assert security._is_self_module_invocation(["python", "-m", _WARD, _TOK], 0)
        assert security._has_self_importing_inline_program(["python", "-c", f"import {_WARD}"], 0)


class TestHookGate:
    """The commands the CLI's own name reaches the gate with, end to end."""

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template",
        [
            "<p> <t>",
            "<p> restart",
            "<p> update",
            "<p> gateway restart",
            "<p> cloud destroy",
            "<p> cron adopt job-1",
            "<pk> -f <p>",
            "~/.local/bin/<p> <t> --port 5476",
        ],
    )
    def test_the_gate_denies_the_self_protected_commands(self, template, prog):
        cmd = _expand(template, prog)
        mgr = HookManager(HooksConfig())
        result = mgr.on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert result.action == TOOL_DENY, cmd

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "template", ["<p> doctor", "<p> status", "echo <p> <t>", "cd <p>-docs"]
    )
    def test_the_gate_does_not_deny_ordinary_use(self, template, prog):
        cmd = _expand(template, prog)
        mgr = HookManager(HooksConfig())
        result = mgr.on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert result.action != TOOL_DENY, cmd

    @pytest.mark.parametrize("prog", _PROGRAMS)
    @pytest.mark.parametrize(
        "rule_id,template",
        [
            (_MINT, "<p> <t>"),
            (_KILL, "<pk> -f <p>"),
            (_RESTART, "<p> restart"),
            (_UPDATE, "<p> update"),
            (_GATEWAY_RESTART, "<p> gateway restart"),
            (_CLOUD, "<p> cloud destroy"),
            (_CRON_ADOPT, "<p> cron adopt job-1"),
        ],
    )
    def test_an_operator_opt_out_of_a_rule_covers_every_spelling(self, rule_id, template, prog):
        """A disabled rule stays disabled -- the floor must not outlive its own opt-out."""
        cmd = _expand(template, prog)
        mgr = HookManager(HooksConfig(denied_commands_disabled_ids=[rule_id]))
        result = mgr.on_tool_call(
            cmd, session_key="probe", tool_kind="execute", command=cmd, is_shell=True
        )
        assert result.action != TOOL_DENY, f"{rule_id} opt-out not honoured for {cmd!r}"
        effective = compute_effective_denied(BUILTIN_DENIED_RULES, (rule_id,), False, (), ())
        assert is_denied(cmd, denied_regexes=effective) is None
