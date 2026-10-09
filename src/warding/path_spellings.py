"""How a harness reads a path argument, for the gates that must agree with it.

The PreToolUse gate judges the string a harness put in a tool call, but the harness
may read a different path out of that string: Claude Code trims JavaScript whitespace
(including U+FEFF, which Python's ``str.strip`` does not remove) before it expands and
opens a path, so ``"<BOM>/data/security_policy.json"`` is a different string to the
gate and the same file to the harness. A gate that checks only the string as written is
decided by whichever of the two readers it picked.

This module imports nothing from the package so that ``hooks`` and
``platform.governance`` (which cannot import each other) share one definition.
"""

from __future__ import annotations

from typing import Sequence

#: The characters JavaScript's ``String.prototype.trim`` removes: the WhiteSpace and
#: LineTerminator productions of ECMAScript, with U+FEFF (the byte-order mark) among
#: them. Python's own whitespace set differs from it at U+FEFF, so neither stands in
#: for the other.
_HARNESS_TRIM_CHARS = "".join(
    chr(code)
    for code in (
        0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0xA0, 0x1680,
        *range(0x2000, 0x200B),
        0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF,
    )
)  # fmt: skip

#: How many paths one call may name, and how long each may be. A real call names a few
#: files, and no filesystem accepts a path past 4096 characters. The raw entry count
#: of a path/location list is bounded too, so duplicates and non-path objects cannot
#: evade the scan bound. A call beyond either limit is denied; checks are linear
#: per path, so an unbounded list would stall the event loop the gate runs on. The gate
#: DENIES such a call rather than checking a truncated prefix, because a truncated check
#: would let the unchecked tail carry the forbidden path.
MAX_TARGET_PATHS = 2048
MAX_TARGET_PATH_CHARS = 4096

# A raw path/location list past the entry bound may contain only duplicates or
# non-path objects. Preserve its denial across cache merges and deduplication
# with an overlong string, which the existing path-length gate always refuses.
# No filesystem operation is ever attempted on this value.
PATH_LIMIT_SENTINEL = "!" * (MAX_TARGET_PATH_CHARS + 1)


def path_spellings(value: str) -> tuple[str, ...]:
    """*value* as written, plus the path a trimming harness reads out of it.

    The second spelling is present only when trimming changes the string. Callers check
    every spelling and deny if any is forbidden, so adding one can only make the gate
    stricter.
    """
    trimmed = value.strip(_HARNESS_TRIM_CHARS)
    if trimmed and trimmed != value:
        return (value, trimmed)
    return (value,)


def exceeds_path_limits(paths: Sequence[str]) -> bool:
    """Whether a call names more paths, or a longer one, than a file operation can."""
    return len(paths) > MAX_TARGET_PATHS or any(len(p) > MAX_TARGET_PATH_CHARS for p in paths)
