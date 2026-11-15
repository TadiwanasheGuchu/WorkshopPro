import io
import threading
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import cli
from app.db.session import get_sessionmaker
from app.models import AuditLog, Organisation, User
from app.services import numbering
from tests.conftest import PASSWORD, Api, OrgFixture

# --------------------------------------------------------------------------- profile & settings


def test_update_profile_and_settings_are_audited(owner_api: Api, db: Session) -> None:
    res = owner_api.patch(
        "/organisation",
        json={"name": "Kalahari Motors CC", "phone": " 061 222 333 ", "website": ""},
    )
    assert res.status_code == 200
    assert res.json()["phone"] == "061 222 333"
    assert res.json()["website"] is None

    settings = owner_api.patch("/organisation/settings", json={"date_format": "YYYY-MM-DD"})
    assert settings.json()["date_format"] == "YYYY-MM-DD"
    assert settings.json()["currency_code"] == "NAD"

    actions = db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)).all()
    assert "organisation.updated" in actions
    assert "organisation.settings_updated" in actions
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "organisation.updated")).one()
    assert entry.changes["name"] == ["Kalahari Motors", "Kalahari Motors CC"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/organisation", {"name": None}),
        ("/organisation", {"name": "  "}),
        ("/organisation", {"unknown_field": "x"}),
        ("/organisation/settings", {"timezone": "Mars/Olympus"}),
        ("/organisation/settings", {"currency_code": "nad"}),
        ("/organisation/settings", {"date_format": "D/M/YY"}),
    ],
)
def test_invalid_organisation_updates_rejected(
    owner_api: Api, path: str, body: dict[str, Any]
) -> None:
    assert owner_api.patch(path, json=body).status_code == 422


# --------------------------------------------------------------------------- tax rates


def test_no_tax_rate_is_preconfigured(owner_api: Api) -> None:
    assert owner_api.get("/organisation/tax-rates").json() == []


def test_tax_rates_single_default(owner_api: Api) -> None:
    a = owner_api.post(
        "/organisation/tax-rates",
        json={"name": "Standard", "rate_percent": "15.00", "is_default": True},
    ).json()
    b = owner_api.post(
        "/organisation/tax-rates",
        json={"name": "Zero rated", "rate_percent": "0", "is_default": True},
    ).json()
    assert a["rate_percent"] == "15.00"

    rates = {r["name"]: r for r in owner_api.get("/organisation/tax-rates").json()}
    assert rates["Standard"]["is_default"] is False
    assert rates["Zero rated"]["is_default"] is True

    owner_api.patch(f"/organisation/tax-rates/{a['id']}", json={"is_default": True})
    rates = {r["name"]: r for r in owner_api.get("/organisation/tax-rates").json()}
    assert rates["Standard"]["is_default"] is True
    assert rates["Zero rated"]["is_default"] is False

    deactivated = owner_api.patch(f"/organisation/tax-rates/{a['id']}", json={"is_active": False})
    assert deactivated.json()["is_default"] is False
    assert b["id"]


@pytest.mark.parametrize("rate", ["100.01", "-1", "15.123", "abc"])
def test_invalid_tax_rates_rejected(owner_api: Api, rate: str) -> None:
    res = owner_api.post("/organisation/tax-rates", json={"name": "Bad", "rate_percent": rate})
    assert res.status_code == 422


def test_duplicate_tax_rate_name_conflicts(owner_api: Api) -> None:
    owner_api.post("/organisation/tax-rates", json={"name": "Standard", "rate_percent": "15"})
    dup = owner_api.post("/organisation/tax-rates", json={"name": "Standard", "rate_percent": "10"})
    assert dup.status_code == 409


# --------------------------------------------------------------------------- numbering


def test_document_sequences_seeded_and_editable(owner_api: Api) -> None:
    seqs = {s["document_type"]: s for s in owner_api.get("/organisation/document-sequences").json()}
    assert seqs["job_card"]["example"] == "JC-000001"
    assert seqs["invoice"]["example"] == "INV-000001"

    res = owner_api.patch(
        "/organisation/document-sequences/job_card",
        json={"prefix": "JOB", "padding": 5, "next_number": 1200},
    )
    assert res.json()["example"] == "JOB-01200"

    lower = owner_api.patch("/organisation/document-sequences/job_card", json={"next_number": 5})
    assert lower.status_code == 409
    bad_prefix = owner_api.patch(
        "/organisation/document-sequences/job_card", json={"prefix": "jc!"}
    )
    assert bad_prefix.status_code == 422
    unknown = owner_api.patch("/organisation/document-sequences/banana", json={"padding": 3})
    assert unknown.status_code == 422


def test_concurrent_number_allocation_is_unique_and_gap_free(org: OrgFixture) -> None:
    results: list[str] = []
    lock = threading.Lock()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(5):
                with get_sessionmaker()() as session:
                    number = numbering.allocate(session, org.id, numbering.DocumentType.JOB_CARD)
                    session.commit()
                with lock:
                    results.append(number)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert sorted(results) == [f"JC-{n:06d}" for n in range(1, 41)]


# --------------------------------------------------------------------------- branches


def test_branch_lifecycle(owner_api: Api, db: Session) -> None:
    created = owner_api.post(
        "/branches", json={"name": "Swakopmund", "code": "swk-01", "email": "swk@example.com"}
    )
    assert created.status_code == 201, created.text
    branch = created.json()
    assert branch["code"] == "SWK-01"
    assert [h["weekday"] for h in branch["operating_hours"]] == list(range(7))
    assert branch["operating_hours"][6]["is_closed"] is True

    dup = owner_api.post("/branches", json={"name": "Other", "code": "SWK-01"})
    assert dup.status_code == 409

    hours = [
        {"weekday": d, "is_closed": False, "opens_at": "07:30", "closes_at": "17:30"}
        for d in range(6)
    ] + [{"weekday": 6, "is_closed": True}]
    res = owner_api.put(f"/branches/{branch['id']}/operating-hours", json={"days": hours})
    assert res.status_code == 200
    assert res.json()[0]["opens_at"] == "07:30:00"

    archived = owner_api.post(f"/branches/{branch['id']}/archive").json()
    assert archived["archived_at"] is not None
    listed = owner_api.get("/branches").json()["items"]
    assert branch["id"] not in {b["id"] for b in listed}
    with_archived = owner_api.get("/branches", params={"include_archived": True}).json()["items"]
    assert branch["id"] in {b["id"] for b in with_archived}
    assert owner_api.post(f"/branches/{branch['id']}/restore").json()["archived_at"] is None


@pytest.mark.parametrize(
    "days",
    [
        [{"weekday": d, "is_closed": True} for d in range(6)],  # only six days
        [{"weekday": 0, "is_closed": True}] * 7,  # duplicates
        [
            {"weekday": d, "is_closed": False, "opens_at": "17:00", "closes_at": "08:00"}
            for d in range(7)
        ],
        [{"weekday": d, "is_closed": False} for d in range(7)],  # missing times
    ],
)
def test_invalid_operating_hours_rejected(owner_api: Api, org: OrgFixture, days: list[Any]) -> None:
    res = owner_api.put(f"/branches/{org.branch_id}/operating-hours", json={"days": days})
    assert res.status_code == 422


def test_cannot_archive_last_active_branch(owner_api: Api, org: OrgFixture) -> None:
    assert owner_api.post(f"/branches/{org.branch_id}/archive").status_code == 409


def test_service_bays(owner_api: Api, org: OrgFixture) -> None:
    base = f"/branches/{org.branch_id}/service-bays"
    bay = owner_api.post(base, json={"name": "Bay 1", "description": "2-post lift"}).json()
    assert owner_api.post(base, json={"name": "Bay 1"}).status_code == 409
    retired = owner_api.patch(f"{base}/{bay['id']}", json={"is_active": False}).json()
    assert retired["is_active"] is False
    assert [b["name"] for b in owner_api.get(base).json()] == ["Bay 1"]

    other = owner_api.post("/branches", json={"name": "Walvis Bay", "code": "WVB"}).json()
    wrong_branch = owner_api.patch(
        f"/branches/{other['id']}/service-bays/{bay['id']}", json={"name": "Moved"}
    )
    assert wrong_branch.status_code == 409


# --------------------------------------------------------------------------- audit log


def test_audit_log_is_append_only(owner_api: Api, db: Session) -> None:
    entry_id = db.scalars(select(AuditLog.id)).first()
    for statement in (
        "UPDATE audit_logs SET summary = 'x' WHERE id = :id",
        "DELETE FROM audit_logs WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(statement), {"id": entry_id})
        db.rollback()


def test_audit_log_endpoint_filters_and_records_context(owner_api: Api) -> None:
    owner_api.patch("/organisation", json={"phone": "061 000 000"})

    res = owner_api.get("/audit-logs", params={"action": "organisation."}).json()
    assert res["total"] >= 2  # created + updated
    latest = res["items"][0]
    assert latest["action"] == "organisation.updated"
    assert latest["actor_name"] == "Olivia Owner"
    assert latest["request_id"]

    logins = owner_api.get("/audit-logs", params={"action": "auth.login"}).json()
    assert logins["total"] == 1


# --------------------------------------------------------------------------- CLI


def test_cli_creates_organisation(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{PASSWORD}\n"))

    code = cli.main(
        [
            "create-organisation",
            "--name",
            "Oshana Auto Repairs",
            "--owner-email",
            "Owner@Oshana.example",
            "--owner-name",
            "Ndapandula Shikongo",
            "--branch-code",
            "osh",
            "--password-stdin",
        ]
    )

    assert code == 0
    assert "can now sign in" in capsys.readouterr().out
    assert db.scalar(select(Organisation.name)) == "Oshana Auto Repairs"
    assert db.scalar(select(User.email)) == "owner@oshana.example"


def test_cli_rejects_weak_password_and_duplicate_email(
    org: OrgFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    args = [
        "create-organisation",
        "--name",
        "X",
        "--owner-email",
        "a@example.com",
        "--owner-name",
        "A",
        "--password-stdin",
    ]
    assert cli.main(args) == 2

    monkeypatch.setattr("sys.stdin", io.StringIO(f"{PASSWORD}\n"))
    dup = [
        "create-organisation",
        "--name",
        "X",
        "--owner-email",
        org.owner_email,
        "--owner-name",
        "A",
        "--password-stdin",
    ]
    assert cli.main(dup) == 1
