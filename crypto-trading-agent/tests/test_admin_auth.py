"""Admin authorization — fail-closed.

Regression for the fail-OPEN default: `require_admin` (and the `is_admin` flag it mirrors)
let ANY logged-in user control the AI engine whenever ADMIN_USER_IDS was empty — which is
the deployed default, since render.yaml never declared it. The engine switch governs LLM
burn, so "any user is admin" is both a cost and a trust problem.

These call the dependency function directly with an explicit principal, bypassing FastAPI's
Depends wiring, and monkeypatch the module-level allow-list.
"""
import pytest
from fastapi import HTTPException

import src.api.server as server


def test_end_user_is_not_admin_when_allowlist_empty(monkeypatch):
    """The core fix: an empty allow-list grants NO end-user admin in a real (auth-on)
    deployment, where principals are 'user', not 'anonymous'."""
    monkeypatch.setattr(server, "ADMIN_USER_IDS", set())
    with pytest.raises(HTTPException) as exc:
        server.require_admin(principal={"kind": "user", "user_id": "user-x"})
    assert exc.value.status_code == 403


def test_listed_owner_is_admin(monkeypatch):
    monkeypatch.setattr(server, "ADMIN_USER_IDS", {"owner-1"})
    assert server.require_admin(principal={"kind": "user", "user_id": "owner-1"}) == "owner-1"


def test_unlisted_user_is_rejected_even_with_an_allowlist(monkeypatch):
    monkeypatch.setattr(server, "ADMIN_USER_IDS", {"owner-1"})
    with pytest.raises(HTTPException):
        server.require_admin(principal={"kind": "user", "user_id": "user-x"})


def test_service_token_is_always_admin(monkeypatch):
    monkeypatch.setattr(server, "ADMIN_USER_IDS", set())
    assert server.require_admin(principal={"kind": "service"}) == "service"


def test_anonymous_principal_is_admin_only_in_no_auth_dev(monkeypatch):
    """`anonymous` is emitted only when no auth is configured at all (local dev), so it may
    stay admin without opening a hole in a deployment that has auth on."""
    monkeypatch.setattr(server, "ADMIN_USER_IDS", set())
    assert server.require_admin(principal={"kind": "anonymous"}) == "anonymous"


@pytest.mark.parametrize("principal,allowlist,expected", [
    ({"kind": "user", "user_id": "user-x"}, set(), False),
    ({"kind": "user", "user_id": "owner-1"}, {"owner-1"}, True),
    ({"kind": "user", "user_id": "user-x"}, {"owner-1"}, False),
    ({"kind": "service"}, set(), True),
    ({"kind": "anonymous"}, set(), True),
])
def test_is_admin_flag_stays_in_lockstep_with_require_admin(
    monkeypatch, principal, allowlist, expected
):
    """GET /api/engine's `is_admin` decides whether the dashboard SHOWS the engine toggle;
    require_admin decides whether POST /api/engine ACCEPTS it. If they drift, the UI either
    hides a control the owner has, or shows one that 403s. Pin both to the same table by
    calling the real endpoint function and the real dependency."""
    import asyncio

    monkeypatch.setattr(server, "ADMIN_USER_IDS", allowlist)
    monkeypatch.setattr(server, "_engine_switch", lambda: None)

    status_obj = asyncio.run(server.get_engine(principal=principal))
    assert status_obj["is_admin"] is expected

    if expected:
        server.require_admin(principal=principal)  # must not raise
    else:
        with pytest.raises(HTTPException):
            server.require_admin(principal=principal)
