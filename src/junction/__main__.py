"""Entry point for ``python -m junction``.

``_ensure_ssl_certs()`` MUST run before ``from junction.cli import main``
because importing ``cli`` can still reach ``aiohttp`` transitively (e.g. via
``cli_doctor`` → ``dashboard.crash_dump_store`` / ``dashboard.origin``).
cli.py defers its heaviest aiohttp edges (``cli_server``,
``dashboard.state``) to call time, which makes this ordering EASIER to hold —
but any module-scope import that reaches aiohttp, now or later, must still
execute after ``_ensure_ssl_certs()``, so the prelude stays mandatory.

aiohttp caches its default SSL context at import time
(``aiohttp.connector._SSL_CONTEXT_VERIFIED``).  On AL2 and similar hosts the
bundled interpreter's CA file is missing, so the cached context ends up with zero CA
certs and every HTTPS connection fails with CERTIFICATE_VERIFY_FAILED.
"""

from __future__ import annotations

from junction import platform_compat
from junction._ssl_compat import _ensure_ssl_certs

# Windows: force UTF-8 stdout/stderr before any non-ASCII output (no-op on POSIX).
platform_compat.ensure_utf8_console()
_ensure_ssl_certs()

if __name__ == "__main__":
    from junction.cli import main  # noqa: E402

    main()
