"""Fail-closed network defaults (C5).

Wired through the shared ``hex-service-kit`` rules; these tests prove THIS repo's wiring
(each red against the pre-adoption behaviour: unconditional 0.0.0.0 bind and a dev-origin
CORS fallback in every profile).
"""

from __future__ import annotations

import dataclasses
import importlib
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER

from market_intelligence.api import app as app_module

_FRAME_ENV = "MKT_INTEL_FRAME_ANCESTORS"


@pytest.fixture
def app_with_frame_ancestors(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[str | None], ModuleType]]:
    """Rebuild the app module with ``MKT_INTEL_FRAME_ANCESTORS`` in a chosen state.

    The header value is resolved once at import, which is what makes it a boot-time posture,
    so proving the three states means re-importing. The module is restored on teardown.
    """

    def build(raw: str | None) -> ModuleType:
        if raw is None:
            monkeypatch.delenv(_FRAME_ENV, raising=False)
        else:
            monkeypatch.setenv(_FRAME_ENV, raw)
        return importlib.reload(app_module)

    yield build
    monkeypatch.undo()
    importlib.reload(app_module)


def _origins_for_profile(
    monkeypatch: pytest.MonkeyPatch, profile: str, *, explicit: bool = True
) -> list[str]:
    monkeypatch.delenv("MKT_INTEL_CORS_ORIGINS", raising=False)
    settings = dataclasses.replace(
        app_module.deps.get_settings(), profile=profile, profile_explicit=explicit
    )
    monkeypatch.setattr(app_module.deps, "get_settings", lambda: settings)
    return app_module._cors_origins()


def test_cors_fallback_only_under_local_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _origins_for_profile(monkeypatch, "local") == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert _origins_for_profile(monkeypatch, "gcp") == []
    assert _origins_for_profile(monkeypatch, "platform") == []


def test_cors_fallback_needs_a_local_profile_that_was_actually_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An inherited ``local`` is not consent to trust arbitrary local processes."""
    assert _origins_for_profile(monkeypatch, "local", explicit=False) == []


def test_explicit_allowlist_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MKT_INTEL_CORS_ORIGINS", "https://tenant.example")
    assert app_module._cors_origins() == ["https://tenant.example"]


def test_an_emptied_cors_allowlist_denies_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set-and-empty is a configuration, not an omission.

    Red against a two-state read, which took the empty string for unset and handed back the
    localhost dev origins the operator had just removed.
    """
    monkeypatch.setenv("MKT_INTEL_CORS_ORIGINS", "")
    settings = dataclasses.replace(
        app_module.deps.get_settings(), profile="local", profile_explicit=True
    )
    monkeypatch.setattr(app_module.deps, "get_settings", lambda: settings)
    assert app_module._cors_origins() == []


def test_unset_frame_ancestors_keeps_the_self_default(
    app_with_frame_ancestors: Callable[[str | None], ModuleType],
) -> None:
    module = app_with_frame_ancestors(None)
    headers = TestClient(module.app, client=LOOPBACK_PEER).get("/healthz").headers
    assert headers["content-security-policy"] == "frame-ancestors 'self'"
    assert headers["x-frame-options"] == "SAMEORIGIN"


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_emptied_frame_ancestors_refuses_framing_rather_than_dropping_the_directive(
    app_with_frame_ancestors: Callable[[str | None], ModuleType], raw: str
) -> None:
    """Red before the three-state read, on both headers at once.

    The old code interpolated the empty value straight into the header, so the response
    carried ``frame-ancestors`` with an EMPTY directive, which browsers discard as a parse
    error; and the ``== "'self'"`` branch was skipped, so no ``X-Frame-Options`` went out
    either. Emptying the allowlist silently removed the clickjacking control instead of
    tightening it.
    """
    module = app_with_frame_ancestors(raw)
    headers = TestClient(module.app, client=LOOPBACK_PEER).get("/healthz").headers
    assert headers["content-security-policy"] == "frame-ancestors 'none'"
    assert headers["x-frame-options"] == "DENY"


def test_a_named_frame_ancestors_allowlist_is_used_as_configured(
    app_with_frame_ancestors: Callable[[str | None], ModuleType],
) -> None:
    module = app_with_frame_ancestors("  https://portal.example   https://admin.example  ")
    headers = TestClient(module.app, client=LOOPBACK_PEER).get("/healthz").headers
    assert headers["content-security-policy"] == (
        "frame-ancestors https://portal.example https://admin.example"
    )
    # No X-Frame-Options can express a named allowlist, so none is sent.
    assert "x-frame-options" not in headers


def test_local_profile_refuses_non_loopback_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    from hex_service_kit import InsecureBindError, resolve_bind_host

    monkeypatch.setenv("MKT_INTEL_API_HOST", "0.0.0.0")
    monkeypatch.delenv("MKT_INTEL_ALLOW_INSECURE_DEMO", raising=False)
    with pytest.raises(InsecureBindError):
        resolve_bind_host(
            "local",
            host_env="MKT_INTEL_API_HOST",
            insecure_demo_env="MKT_INTEL_ALLOW_INSECURE_DEMO",
        )


def test_api_still_serves() -> None:
    client = TestClient(app_module.app, client=LOOPBACK_PEER)
    assert client.get("/healthz").status_code == 200
