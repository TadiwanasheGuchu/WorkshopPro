import re
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.integrations.email import InMemoryEmailSender
from app.models import AuditLog, User, UserSession, UserToken
from app.permissions.catalogue import ALL_PERMISSION_CODES
from tests.conftest import PASSWORD, Api, OrgFixture

NEW_PASSWORD = "a-brand-new-passphrase"


def _token_from(outbox: InMemoryEmailSender) -> str:
    match = re.search(r"#token=([A-Za-z0-9_-]+)", outbox.outbox[-1].text)
    assert match, "no token link in email"
    return match.group(1)


# --------------------------------------------------------------------------- sign-in


def test_login_sets_secure_cookies_and_me_returns_owner(org: OrgFixture, new_api: Any) -> None:
    api: Api = new_api()

    res = api.login(org.owner_email)

    assert res.status_code == 204
    cookies = res.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("wp_session="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    csrf_cookie = next(c for c in cookies if c.startswith("wp_csrf="))
    assert "HttpOnly" not in csrf_cookie

    me = api.get("/auth/me").json()
    assert me["email"] == org.owner_email
    assert me["is_owner"] is True
    assert set(me["permissions"]) == ALL_PERMISSION_CODES
    assert [b["code"] for b in me["branches"]] == ["MAIN"]
    assert me["organisation"]["currency_code"] == "NAD"
    assert me["organisation"]["timezone"] == "Africa/Windhoek"


def test_login_failures_share_one_message(org: OrgFixture, new_api: Any, db: Session) -> None:
    api: Api = new_api()

    wrong = api.login(org.owner_email, "not-the-password")
    unknown = api.login("nobody@example.com", "whatever-password")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    failed = db.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed")).all()
    assert len(failed) == 1
    assert failed[0].changes == {"reason": "wrong_password"}


def test_email_is_case_insensitive(org: OrgFixture, new_api: Any) -> None:
    assert new_api().login(org.owner_email.upper()).status_code == 204


def test_deactivated_user_cannot_sign_in(org: OrgFixture, new_api: Any) -> None:
    org.add_user("gone@example.com", [(org.role("mechanic"), org.branch_id)], is_active=False)
    res = new_api().login("gone@example.com")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_invited_user_without_password_cannot_sign_in(org: OrgFixture, new_api: Any) -> None:
    org.add_user("pending@example.com", [(org.role("mechanic"), org.branch_id)], password=None)
    assert new_api().login("pending@example.com", "anything-at-all").status_code == 401


def test_unauthenticated_requests_get_401(new_api: Any, db: Session) -> None:
    res = new_api().get("/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "not_authenticated"


def test_login_is_rate_limited_per_email(
    org: OrgFixture, new_api: Any, settings_override: Any
) -> None:
    settings_override(login_attempts_per_email=3)
    api: Api = new_api()
    for _ in range(3):
        assert api.login(org.owner_email, "wrong-password").status_code == 401

    blocked = api.login(org.owner_email)  # correct password, still blocked

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


# --------------------------------------------------------------------------- CSRF


def test_state_change_without_csrf_header_is_rejected(owner_api: Api) -> None:
    res = owner_api.client.post("/api/v1/auth/logout")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "csrf_failed"


def test_csrf_token_must_belong_to_the_session(owner_api: Api) -> None:
    # Attacker-chosen value placed in both cookie and header (e.g. via a sibling subdomain).
    owner_api.client.cookies.set("wp_csrf", "attacker-controlled-token-value")
    res = owner_api.client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": "attacker-controlled-token-value"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "permission_denied"


def test_csrf_endpoint_returns_session_token_when_signed_in(owner_api: Api) -> None:
    expected = owner_api.client.cookies.get("wp_csrf")
    owner_api.client.cookies.delete("wp_csrf")

    token = owner_api.get("/auth/csrf").json()["csrf_token"]

    assert token == expected
    assert owner_api.post("/auth/logout").status_code == 204


# --------------------------------------------------------------------------- sessions


def test_logout_revokes_session(owner_api: Api) -> None:
    session_cookie = owner_api.client.cookies.get("wp_session")
    assert owner_api.post("/auth/logout").status_code == 204

    owner_api.client.cookies.set("wp_session", session_cookie)  # replay old cookie
    assert owner_api.get("/auth/me").status_code == 401


def test_idle_session_expires(owner_api: Api, db: Session, settings_override: Any) -> None:
    db.execute(update(UserSession).values(last_seen_at=utcnow() - timedelta(hours=13)))
    db.commit()
    assert owner_api.get("/auth/me").status_code == 401


def test_absolute_session_lifetime(owner_api: Api, db: Session) -> None:
    db.execute(update(UserSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert owner_api.get("/auth/me").status_code == 401


def test_deactivation_ends_active_sessions_immediately(
    org: OrgFixture, owner_api: Api, new_api: Any
) -> None:
    user = org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    assert mech.login("mech@example.com").status_code == 204

    assert owner_api.post(f"/users/{user.id}/deactivate").status_code == 200

    assert mech.get("/auth/me").status_code == 401


def test_session_token_is_stored_hashed(owner_api: Api, db: Session) -> None:
    raw = owner_api.client.cookies.get("wp_session")
    stored = db.scalars(select(UserSession.token_hash)).all()
    assert raw not in stored
    assert all(len(h) == 64 for h in stored)


# --------------------------------------------------------------------------- password reset


def test_password_reset_flow(
    org: OrgFixture, owner_api: Api, new_api: Any, outbox: InMemoryEmailSender, db: Session
) -> None:
    anon: Api = new_api()
    assert (
        anon.post("/auth/password-reset/request", json={"email": org.owner_email}).status_code
        == 202
    )
    token = _token_from(outbox)
    assert outbox.outbox[-1].to == org.owner_email

    info = anon.post("/auth/tokens/inspect?purpose=password_reset", json={"token": token})
    assert info.status_code == 200
    assert info.json()["email"] == org.owner_email

    res = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert res.status_code == 204

    # Existing sessions are signed out; the old password no longer works.
    assert owner_api.get("/auth/me").status_code == 401
    assert new_api().login(org.owner_email).status_code == 401
    assert new_api().login(org.owner_email, NEW_PASSWORD).status_code == 204

    # Token is single-use.
    reuse = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "another-password-1"}
    )
    assert reuse.status_code == 400
    assert reuse.json()["error"]["code"] == "invalid_token"


def test_password_reset_for_unknown_email_looks_identical(
    new_api: Any, outbox: InMemoryEmailSender, db: Session
) -> None:
    res = new_api().post("/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert res.status_code == 202
    assert outbox.outbox == []


def test_new_reset_request_invalidates_previous_link(
    org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    anon: Api = new_api()
    anon.post("/auth/password-reset/request", json={"email": org.owner_email})
    first = _token_from(outbox)
    anon.post("/auth/password-reset/request", json={"email": org.owner_email})

    res = anon.post(
        "/auth/password-reset/confirm", json={"token": first, "new_password": NEW_PASSWORD}
    )
    assert res.status_code == 400


def test_expired_reset_token_is_rejected(
    org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender, db: Session
) -> None:
    anon: Api = new_api()
    anon.post("/auth/password-reset/request", json={"email": org.owner_email})
    token = _token_from(outbox)
    db.execute(update(UserToken).values(expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()

    res = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert res.status_code == 400


def test_reset_token_cannot_accept_invitation(
    org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    anon: Api = new_api()
    anon.post("/auth/password-reset/request", json={"email": org.owner_email})
    token = _token_from(outbox)
    res = anon.post("/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD})
    assert res.status_code == 400


def test_short_password_rejected(org: OrgFixture, owner_api: Api) -> None:
    res = owner_api.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert res.status_code == 422


# --------------------------------------------------------------------------- invitations


def test_invitation_flow(
    org: OrgFixture, owner_api: Api, new_api: Any, outbox: InMemoryEmailSender, db: Session
) -> None:
    mechanic = org.role("mechanic")
    res = owner_api.post(
        "/users",
        json={
            "email": "Tjiuee@Example.com",
            "full_name": "Tjiuee Kaura",
            "role_assignments": [{"role_id": str(mechanic.id), "branch_id": str(org.branch_id)}],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "invited"
    assert outbox.outbox[-1].to.lower() == "tjiuee@example.com"
    token = _token_from(outbox)

    anon: Api = new_api()
    info = anon.post("/auth/tokens/inspect?purpose=invitation", json={"token": token}).json()
    assert info["full_name"] == "Tjiuee Kaura"
    assert info["organisation_name"] == "Kalahari Motors"

    assert (
        anon.post(
            "/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD}
        ).status_code
        == 204
    )
    assert new_api().login("tjiuee@example.com", NEW_PASSWORD).status_code == 204
    user = db.scalars(select(User).where(User.email == "tjiuee@example.com")).one()
    db.refresh(user)
    assert user.activated_at is not None

    again = anon.post("/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD})
    assert again.status_code == 400


def test_resend_invitation_revokes_old_link(
    org: OrgFixture, owner_api: Api, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    res = owner_api.post(
        "/users",
        json={
            "email": "new@example.com",
            "full_name": "New Person",
            "role_assignments": [{"role_id": str(org.role("mechanic").id)}],
        },
    )
    user_id = res.json()["id"]
    first = _token_from(outbox)
    assert owner_api.post(f"/users/{user_id}/resend-invitation").status_code == 202
    second = _token_from(outbox)

    anon: Api = new_api()
    assert (
        anon.post(
            "/auth/invitations/accept", json={"token": first, "password": NEW_PASSWORD}
        ).status_code
        == 400
    )
    assert (
        anon.post(
            "/auth/invitations/accept", json={"token": second, "password": NEW_PASSWORD}
        ).status_code
        == 204
    )


# --------------------------------------------------------------------------- password change


def test_change_password_signs_out_other_sessions(org: OrgFixture, new_api: Any) -> None:
    phone: Api = new_api()
    desktop: Api = new_api()
    phone.login(org.owner_email)
    desktop.login(org.owner_email)

    res = desktop.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )

    assert res.status_code == 204
    assert desktop.get("/auth/me").status_code == 200
    assert phone.get("/auth/me").status_code == 401


def test_change_password_requires_current_password(owner_api: Api) -> None:
    res = owner_api.post(
        "/auth/password", json={"current_password": "wrong-one!", "new_password": NEW_PASSWORD}
    )
    assert res.status_code == 401
