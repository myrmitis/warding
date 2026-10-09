"""Representative fixtures for adapter + blast-radius tests."""

import os
import tempfile


def _symlinks_creatable() -> bool:
    """Whether this platform lets an unprivileged process create a symlink.

    Windows grants SeCreateSymbolicLinkPrivilege only to an administrator or a
    Developer Mode account, so on such a host the planted-link tests cannot even
    stage their attack. The guard those tests cover runs everywhere -- only
    staging the plant is privileged.
    """
    with tempfile.TemporaryDirectory() as d:
        probe = os.path.join(d, "probe")
        try:
            os.symlink(d, probe)
        except (OSError, NotImplementedError):
            return False
    return True


#: Gate for every test that stages a planted symlink. Probed once per process;
#: importing modules decorate classes and functions at definition time, so this
#: must be a plain constant rather than a fixture.
SYMLINKS_OK = _symlinks_creatable()


# A sensitive file (gateway/lifecycle) with a guard removal + an import add,
# plus a small non-sensitive file — the blast-radius signal fixture.
_SERVER_DIFF = """--- a/src/warding/gateway/server.py
+++ b/src/warding/gateway/server.py
@@ -10,7 +10,9 @@
 import asyncio
+import logging
 def restart(self):
-    if not self._stopping:
-        return
+    self._respawn()
+    self._stopping = False
     pass
"""

_FORMAT_DIFF = """--- a/src/warding/util/format.py
+++ b/src/warding/util/format.py
@@ -1,2 +1,3 @@
-def f(x): pass
+def f(x):
+    return str(x)
"""

# Sensitive-path files (guard removal + import add) for blast-radius signal tests.
SENSITIVE_FILES = [
    {"path": "src/warding/gateway/server.py", "diff": _SERVER_DIFF},
    {"path": "src/warding/util/format.py", "diff": _FORMAT_DIFF},
]

# A tiny, non-sensitive, non-fix change (should rate SMALL).
SMALL_FILES = [{
    "path": "docs/readme.md",
    "diff": "--- a/docs/readme.md\n+++ b/docs/readme.md\n@@ -1 +1,2 @@\n line\n+new line\n",
}]

# A one-line change on a sensitive path, no guards (should rate MEDIUM).
SENSITIVE_TINY_FILES = [{
    "path": "src/auth/session.py",
    "diff": "--- a/src/auth/session.py\n+++ b/src/auth/session.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
}]

# A GitHub PR payload as the worker assembles it from `gh api`: the pulls/{n}
# object merged with a `files` array (each carrying its per-file `patch`) and
# a `comments` list. Mirrors the shape of a pull request on an example repository.
GITHUB_PAYLOAD = {
    "number": 42,
    "title": "Fix deadlock in the widget refresh handler",
    "body": "Refresh hung on a lock round-trip. Fixes #12 by using a local "
            "settings clone instead of a round-trip.",
    "html_url": "https://github.com/acme/widgets/pull/42",
    "state": "open",
    "draft": False,
    "user": {"login": "alice"},
    "base": {"ref": "main", "repo": {"full_name": "acme/widgets"}},
    "head": {"ref": "fix-refresh-deadlock", "sha": "fb58081a1c0ffee0000000000000000000000000"},
    "files": [
        {"filename": "src/widgets/refresh.py",
         "patch": _SERVER_DIFF, "status": "modified"},
        {"filename": "docs/CHANGELOG.md",
         "patch": _FORMAT_DIFF, "status": "modified"},
    ],
    "comments": [{"user": {"login": "reviewer"}, "body": "add a regression test"}],
}
