"""Process-group-safe subprocess helper for the installer test suites.

The installer tests run the real ``cli.sh``, which probes interpreters and
package managers as grandchildren. ``subprocess.run(timeout=...)`` kills only
the process it spawned, and pytest-timeout's signal only unwinds the Python
frame, so a wedged grandchild survives either one: it is reparented to init and
keeps burning a core until someone kills it by hand. Running the child as a
session leader makes the whole tree killable as one process group.

The PowerShell preflight reaches this module on Windows too, so the spawn and the
kill both go through ``platform_compat``: ``os.killpg`` does not exist there, and
an ``AttributeError`` out of the timeout path would turn the preflight's skip into
a failure.
"""

from __future__ import annotations

import subprocess

from warding import platform_compat

#: A hermetic installer run (fake curl, fake package managers) finishes in
#: seconds, so this bound only ever trips on a wedge. It sits well under
#: pytest-timeout's ceiling so that this helper, rather than pytest-timeout, is
#: what reaps the tree.
INSTALLER_TIMEOUT = 60.0


def run_bounded(
    argv: list[str],
    env: dict[str, str],
    timeout: float = INSTALLER_TIMEOUT,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` in its own process group; on timeout kill the whole tree.

    On POSIX ``start_new_session`` makes the child a session leader, so its pid is
    also its process-group id and one group kill reaps every descendant; on
    Windows ``kill_process_tree`` walks the tree with ``taskkill /T``. Re-raises
    ``subprocess.TimeoutExpired`` once the tree is gone.

    ``cwd`` matters when the thing under test resolves a RELATIVE path: an
    installer that bakes one into a generated wrapper can only be caught by
    running it from a known directory.
    """
    with subprocess.Popen(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
        start_new_session=platform_compat.IS_POSIX,
        creationflags=platform_compat.CREATE_NEW_PROCESS_GROUP,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                platform_compat.kill_process_tree(proc.pid, platform_compat.SIGKILL)
            except ProcessLookupError:
                pass  # Exited between the timeout and the kill; nothing to reap.
            proc.communicate()
            raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
