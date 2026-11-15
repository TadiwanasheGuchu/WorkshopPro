"""Authorization: permission enforcement, tenant isolation, privilege escalation."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, RolePermission
from app.permissions.catalogue import P
from tests.conftest import Api, OrgFixture


def _custom_role(org: OrgFixture, name: str, perms: set[str]) -> Role:
    role = Role(organisation_id=org.id, name=name)
    org.db.add(role)
    org.db.flush()
    org.db.add_all(RolePermission(role_id=role.id, permission=p) for p in perms)
    org.db.commit()
    return role


def _login_as(new_api: Any, email: str) -> Api:
    api: Api = new_api()
    assert api.login(email).status_code == 204
    return api


# --------------------------------------------------------------------------- enforcement


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/users", None),
        (
            "POST",
            "/users",
            {
                "email": "x@example.com",
                "full_name": "X",
                "role_assignments": [{"role_id": "00000000-0000-4000-8000-000000000000"}],
            },
        ),
        ("GET", "/roles", None),
        ("POST", "/roles", {"name": "Hacker", "permissions": []}),
        ("GET", "/audit-logs", None),
        ("GET", "/organisation", None),
        ("PATCH", "/organisation", {"name": "Taken over"}),
        ("PATCH", "/organisation/settings", {"currency_code": "USD"}),
        ("POST", "/organisation/tax-rates", {"name": "VAT", "rate_percent": "15"}),
        ("POST", "/branches", {"name": "New", "code": "NEW"}),
    ],
)
def test_mechanic_is_denied_admin_operations(
    org: OrgFixture, new_api: Any, method: str, path: str, body: dict[str, Any] | None
) -> None:
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    api = _login_as(new_api, "mech@example.com")

    res = api.request(method, path, json=body)

    assert res.status_code in (403, 422), res.text
    if res.status_code == 422:
        # Validation runs before the service; resend a valid body to prove the 403.
        pytest.fail(f"{method} {path} body should be valid for this test: {res.text}")
    assert res.json()["error"]["code"] == "permission_denied"


def test_permission_change_applies_on_next_request(
    org: OrgFixture, new_api: Any, db: Session
) -> None:
    role = _custom_role(org, "Front desk", set())
    org.add_user("desk@example.com", [(role, None)])
    api = _login_as(new_api, "desk@example.com")
    assert api.get("/users").status_code == 403

    db.add(RolePermission(role_id=role.id, permission=P.USERS_VIEW))
    db.commit()

    assert api.get("/users").status_code == 200


# --------------------------------------------------------------------------- tenant isolation


def test_cross_organisation_records_are_not_found(make_org: Any, new_api: Any, db: Session) -> None:
    org_a: OrgFixture = make_org("Alpha Auto")
    org_b: OrgFixture = make_org("Beta Panelbeaters")
    victim = org_a.add_user("victim@example.com", [(org_a.role("mechanic"), org_a.branch_id)])
    a_role = org_a.role("mechanic")
    b_owner = _login_as(new_api, org_b.owner_email)

    assert b_owner.get(f"/branches/{org_a.branch_id}").status_code == 404
    assert b_owner.patch(f"/branches/{org_a.branch_id}", json={"name": "Mine"}).status_code == 404
    assert b_owner.get(f"/users/{victim.id}").status_code == 404
    assert b_owner.post(f"/users/{victim.id}/deactivate").status_code == 404
    assert b_owner.get(f"/roles/{a_role.id}").status_code == 404
    assert b_owner.patch(f"/roles/{a_role.id}", json={"name": "x"}).status_code == 404

    emails = {u["email"] for u in b_owner.get("/users").json()["items"]}
    assert emails == {org_b.owner_email}
    branch_ids = {b["id"] for b in b_owner.get("/branches").json()["items"]}
    assert branch_ids == {str(org_b.branch_id)}
    audit_orgs = {e["summary"] for e in b_owner.get("/audit-logs").json()["items"]}
    assert not any("Alpha" in s for s in audit_orgs)


def test_cannot_assign_another_organisations_role_or_branch(make_org: Any, new_api: Any) -> None:
    org_a: OrgFixture = make_org("Alpha Auto")
    org_b: OrgFixture = make_org("Beta Panelbeaters")
    b_owner = _login_as(new_api, org_b.owner_email)

    foreign_role = b_owner.post(
        "/users",
        json={
            "email": "x@example.com",
            "full_name": "X",
            "role_assignments": [{"role_id": str(org_a.role("administrator").id)}],
        },
    )
    foreign_branch = b_owner.post(
        "/users",
        json={
            "email": "y@example.com",
            "full_name": "Y",
            "role_assignments": [
                {"role_id": str(org_b.role("mechanic").id), "branch_id": str(org_a.branch_id)}
            ],
        },
    )
    assert foreign_role.status_code == 422
    assert foreign_branch.status_code == 422


# --------------------------------------------------------------------------- escalation


def test_user_manager_cannot_assign_roles_beyond_own_permissions(
    org: OrgFixture, new_api: Any
) -> None:
    hr = _custom_role(org, "HR", {P.USERS_VIEW, P.USERS_MANAGE})
    org.add_user("hr@example.com", [(hr, None)])
    api = _login_as(new_api, "hr@example.com")

    admin = api.post(
        "/users",
        json={
            "email": "new@example.com",
            "full_name": "New",
            "role_assignments": [{"role_id": str(org.role("administrator").id)}],
        },
    )
    assert admin.status_code == 403
    assert P.SETTINGS_MANAGE in admin.json()["error"]["details"]["missing"]

    allowed = api.post(
        "/users",
        json={
            "email": "mech@example.com",
            "full_name": "Mech",
            "role_assignments": [{"role_id": str(hr.id)}],
        },
    )
    assert allowed.status_code == 201


def test_user_manager_cannot_grant_self_more_roles(org: OrgFixture, new_api: Any) -> None:
    hr = _custom_role(org, "HR", {P.USERS_VIEW, P.USERS_MANAGE})
    me = org.add_user("hr@example.com", [(hr, None)])
    api = _login_as(new_api, "hr@example.com")

    res = api.put(
        f"/users/{me.id}/role-assignments",
        json={
            "role_assignments": [
                {"role_id": str(hr.id)},
                {"role_id": str(org.role("administrator").id)},
            ]
        },
    )
    assert res.status_code == 403


def test_only_owner_can_grant_owner_role(org: OrgFixture, new_api: Any) -> None:
    admin_user = org.add_user("admin@example.com", [(org.role("administrator"), None)])
    api = _login_as(new_api, "admin@example.com")

    res = api.put(
        f"/users/{admin_user.id}/role-assignments",
        json={"role_assignments": [{"role_id": str(org.role("owner").id)}]},
    )
    assert res.status_code == 403


def test_administrator_cannot_modify_owner_account(
    org: OrgFixture, new_api: Any, db: Session
) -> None:
    org.add_user("admin@example.com", [(org.role("administrator"), None)])
    api = _login_as(new_api, "admin@example.com")
    owner_id = api.get("/users", params={"search": org.owner_email}).json()["items"][0]["id"]

    assert api.post(f"/users/{owner_id}/deactivate").status_code == 403
    assert api.patch(f"/users/{owner_id}", json={"email": "evil@example.com"}).status_code == 403
    assert (
        api.put(f"/users/{owner_id}/role-assignments", json={"role_assignments": []}).status_code
        == 403
    )


def test_role_manager_cannot_add_permissions_they_lack(org: OrgFixture, new_api: Any) -> None:
    rm = _custom_role(org, "Role admin", {P.USERS_VIEW, P.ROLES_MANAGE})
    org.add_user("rm@example.com", [(rm, None)])
    api = _login_as(new_api, "rm@example.com")

    create = api.post("/roles", json={"name": "Super", "permissions": [P.SETTINGS_MANAGE]})
    escalate_own = api.patch(
        f"/roles/{rm.id}",
        json={"permissions": [P.USERS_VIEW, P.ROLES_MANAGE, P.USERS_MANAGE]},
    )
    assert create.status_code == 403
    assert escalate_own.status_code == 403

    # Removing permissions or granting held ones is fine.
    ok = api.post("/roles", json={"name": "Viewer", "permissions": [P.USERS_VIEW]})
    assert ok.status_code == 201


def test_owner_role_is_immutable(owner_api: Api, org: OrgFixture) -> None:
    owner_role = org.role("owner")
    assert owner_api.patch(f"/roles/{owner_role.id}", json={"name": "Boss"}).status_code == 409
    assert owner_api.post(f"/roles/{owner_role.id}/archive").status_code == 409


def test_unknown_permission_codes_rejected(owner_api: Api) -> None:
    res = owner_api.post("/roles", json={"name": "Odd", "permissions": ["everything.ever"]})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "unknown_permission"


def test_last_owner_is_protected(owner_api: Api, org: OrgFixture) -> None:
    me = owner_api.get("/auth/me").json()

    assert owner_api.post(f"/users/{me['id']}/deactivate").status_code == 409
    remove_own = owner_api.put(
        f"/users/{me['id']}/role-assignments",
        json={"role_assignments": [{"role_id": str(org.role("administrator").id)}]},
    )
    assert remove_own.status_code == 409
    assert "owner" in remove_own.json()["error"]["message"]


def test_owner_can_hand_over_to_second_owner(owner_api: Api, org: OrgFixture) -> None:
    second = org.add_user("second@example.com", [(org.role("owner"), None)])
    me = owner_api.get("/auth/me").json()

    res = owner_api.put(
        f"/users/{me['id']}/role-assignments",
        json={"role_assignments": [{"role_id": str(org.role("administrator").id)}]},
    )
    assert res.status_code == 200
    assert owner_api.get(f"/users/{second.id}").json()["is_owner"] is True


def test_owner_role_cannot_be_branch_scoped(owner_api: Api, org: OrgFixture) -> None:
    user = org.add_user("x@example.com", [(org.role("mechanic"), org.branch_id)])
    res = owner_api.put(
        f"/users/{user.id}/role-assignments",
        json={
            "role_assignments": [
                {"role_id": str(org.role("owner").id), "branch_id": str(org.branch_id)}
            ]
        },
    )
    assert res.status_code == 422


def test_role_in_use_cannot_be_archived(owner_api: Api, org: OrgFixture) -> None:
    org.add_user("m@example.com", [(org.role("mechanic"), org.branch_id)])
    res = owner_api.post(f"/roles/{org.role('mechanic').id}/archive")
    assert res.status_code == 409


# --------------------------------------------------------------------------- branch scope


def test_branch_scoped_manager_limited_to_own_branch(
    org: OrgFixture, new_api: Any, db: Session
) -> None:
    other = org.add_branch("SWK", "Swakopmund")
    branch_admin = _custom_role(org, "Branch admin", {P.BRANCHES_VIEW, P.BRANCHES_MANAGE})
    org.add_user("bm@example.com", [(branch_admin, org.branch_id)])
    api = _login_as(new_api, "bm@example.com")

    listed = {b["id"] for b in api.get("/branches").json()["items"]}
    assert listed == {str(org.branch_id)}

    assert api.patch(f"/branches/{org.branch_id}", json={"phone": "061 123 456"}).status_code == 200
    assert api.patch(f"/branches/{other.id}", json={"phone": "064 1"}).status_code == 403
    assert api.get(f"/branches/{other.id}").status_code == 403
    # Creating and archiving branches needs an organisation-wide grant.
    assert api.post("/branches", json={"name": "Ondangwa", "code": "OND"}).status_code == 403
    assert api.post(f"/branches/{other.id}/archive").status_code == 403

    me = api.get("/auth/me").json()
    assert me["permissions"] == []
    assert sorted(me["branch_permissions"][str(org.branch_id)]) == sorted(
        [P.BRANCHES_MANAGE, P.BRANCHES_VIEW]
    )
    assert [b["code"] for b in me["branches"]] == ["MAIN"]


def test_branch_grant_never_satisfies_organisation_permission(
    org: OrgFixture, new_api: Any, db: Session
) -> None:
    # A misconfigured role grants an organisation-scoped permission at branch level.
    odd = _custom_role(org, "Odd", {P.USERS_VIEW})
    org.add_user("odd@example.com", [(odd, org.branch_id)])
    api = _login_as(new_api, "odd@example.com")
    assert api.get("/users").status_code == 403


def test_archived_branch_assignments_grant_nothing(
    org: OrgFixture, owner_api: Api, new_api: Any, db: Session
) -> None:
    other = org.add_branch("SWK", "Swakopmund")
    org.add_user("m@example.com", [(org.role("mechanic"), other.id)])
    api = _login_as(new_api, "m@example.com")
    assert api.get("/branches").json()["total"] == 1

    assert owner_api.post(f"/branches/{other.id}/archive").status_code == 200

    assert api.get("/branches").status_code == 403
    assert api.get("/auth/me").json()["branches"] == []


def test_users_listing_is_scoped_and_paginated(owner_api: Api, org: OrgFixture) -> None:
    for i in range(5):
        org.add_user(f"user{i}@example.com", [(org.role("mechanic"), org.branch_id)])
    page = owner_api.get("/users", params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 6
    assert page["page"] == 2
    assert len(page["items"]) == 2
    assert owner_api.get("/users", params={"page_size": 500}).status_code == 422


def test_deactivated_users_roles_do_not_count_as_owner(
    owner_api: Api, org: OrgFixture, db: Session
) -> None:
    second = org.add_user("second@example.com", [(org.role("owner"), None)])
    assert owner_api.post(f"/users/{second.id}/deactivate").status_code == 200
    me = owner_api.get("/auth/me").json()
    # Now the only active owner again: cannot be removed.
    assert owner_api.post(f"/users/{me['id']}/deactivate").status_code == 409
    assert db.scalar(select(Role.id).where(Role.is_owner, Role.organisation_id == org.id))
