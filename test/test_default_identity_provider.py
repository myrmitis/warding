"""The public ``DefaultIdentityProvider`` reports no SSO session."""

from __future__ import annotations

import inspect

import pytest

from junction.platform.defaults import DefaultIdentityProvider


def test_status_reports_unavailable() -> None:
    assert DefaultIdentityProvider().status() == {"available": False}


@pytest.mark.asyncio
async def test_status_line_is_empty_for_any_prefix() -> None:
    provider = DefaultIdentityProvider()
    assert inspect.iscoroutinefunction(provider.status_line)
    assert await provider.status_line() == ""
    assert await provider.status_line(prefix="*NONSENSE-PFX:*") == ""


def test_reserved_and_hook_methods_are_inert() -> None:
    provider = DefaultIdentityProvider()
    assert provider.whoami() is None
    assert provider.issuer() is None
    assert provider.preflight_checks() == []
    assert provider.credential_watch_paths() == []
