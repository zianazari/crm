"""Leads, customers and organizations: access scope, duplicates, conversion.

Covers acceptance criteria 2, 3, 4 and 13 of the spec, with the section 0 rule that
reps see only the current status of records they do not own.
"""

import threading
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.crm.models import Customer, LeadSource, OwnershipHistory
from tests.conftest import Org, login_as


def source_id() -> str:
    with SessionLocal() as db:
        return str(db.scalars(select(LeadSource.id).order_by(LeadSource.sort_order)).first())


def create_lead(client: TestClient, **fields: Any) -> dict[str, Any]:
    body = {"full_name": "علی رضایی", "mobile": "09121111111", **fields}
    response = client.post("/leads", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


# -- visibility ------------------------------------------------------------


def test_rep_sees_own_lead_in_full_and_others_limited(org: Org) -> None:
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)
    own = create_lead(rep1, mobile="09121111111", company_name="شرکت آبان")
    other = create_lead(rep2, full_name="مریم مرادی", mobile="09122222222")

    mine = rep1.get(f"/leads/{own['id']}").json()
    assert mine["access"] == "full" and mine["mobile"] == "+989121111111"

    theirs = rep1.get(f"/leads/{other['id']}").json()
    assert theirs["access"] == "limited"
    assert theirs["status"] == "new" and theirs["owner"]["full_name"] == "کارشناس ۲"
    assert "mobile" not in theirs and "email" not in theirs and "description" not in theirs

    listed = {item["id"]: item["access"] for item in rep1.get("/leads").json()["items"]}
    assert listed == {own["id"]: "full", other["id"]: "limited"}


def test_rep_cannot_change_records_they_do_not_own(org: Org) -> None:
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)
    lead = create_lead(rep2)
    assert rep1.patch(f"/leads/{lead['id']}", json={"full_name": "x y"}).status_code == 403
    assert rep1.post(f"/leads/{lead['id']}/convert", json={}).status_code == 403
    assert rep1.post(f"/leads/{lead['id']}/archive").status_code == 403
    assert rep1.get(f"/leads/{uuid.uuid4()}").status_code == 404


def test_rep_can_only_create_for_themselves(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    response = rep1.post(
        "/leads",
        json={"full_name": "علی رضایی", "mobile": "09121111111", "owner_id": str(org.rep2.id)},
    )
    assert response.status_code == 403


def test_manager_sees_team_in_full_and_other_teams_limited(org: Org) -> None:
    team_lead = create_lead(login_as(org.rep1.id))
    foreign = create_lead(login_as(org.other_rep.id), mobile="09123333333")
    manager = login_as(org.manager.id)
    assert manager.get(f"/leads/{team_lead['id']}").json()["access"] == "full"
    assert manager.get(f"/leads/{foreign['id']}").json()["access"] == "limited"


def test_admin_sees_everything_in_full(org: Org) -> None:
    lead = create_lead(login_as(org.other_rep.id))
    assert login_as(org.admin.id).get(f"/leads/{lead['id']}").json()["access"] == "full"


# -- assignment (criterion 3) -------------------------------------------------


def test_manager_reassigns_within_team_and_previous_owner_loses_access(org: Org) -> None:
    rep1, rep2, manager = login_as(org.rep1.id), login_as(org.rep2.id), login_as(org.manager.id)
    lead = create_lead(rep1)

    response = manager.post(
        f"/leads/{lead['id']}/assign", json={"owner_id": str(org.rep2.id), "reason": "تقسیم کار"}
    )
    assert response.status_code == 200
    assert rep2.get(f"/leads/{lead['id']}").json()["access"] == "full"
    assert rep1.get(f"/leads/{lead['id']}").json()["access"] == "limited"
    assert rep1.patch(f"/leads/{lead['id']}", json={"full_name": "x y"}).status_code == 403

    with SessionLocal() as db:
        history = db.scalars(select(OwnershipHistory)).one()
        assert (history.from_user_id, history.to_user_id) == (org.rep1.id, org.rep2.id)
        assert history.changed_by_id == org.manager.id


def test_manager_cannot_assign_outside_team(org: Org) -> None:
    lead = create_lead(login_as(org.rep1.id))
    manager = login_as(org.manager.id)
    response = manager.post(f"/leads/{lead['id']}/assign", json={"owner_id": str(org.other_rep.id)})
    assert response.status_code == 403
    foreign = create_lead(login_as(org.other_rep.id), mobile="09124444444")
    response = manager.post(f"/leads/{foreign['id']}/assign", json={"owner_id": str(org.rep1.id)})
    assert response.status_code == 403


def test_rep_cannot_reassign_own_lead(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    lead = create_lead(rep1)
    response = rep1.post(f"/leads/{lead['id']}/assign", json={"owner_id": str(org.rep2.id)})
    assert response.status_code == 403


# -- search and filters -----------------------------------------------------


def test_search_by_exact_number_finds_others_in_limited_form_only(org: Org) -> None:
    create_lead(login_as(org.rep2.id), full_name="مریم مرادی", mobile="09125555555")
    rep1 = login_as(org.rep1.id)

    found = rep1.get("/leads", params={"q": "۰۹۱۲۵۵۵۵۵۵۵"}).json()["items"]
    assert [item["access"] for item in found] == ["limited"]
    # A partial number must not match: no fishing for other people's contacts.
    assert rep1.get("/leads", params={"q": "5555"}).json()["items"] == []


def test_filtering_by_source_does_not_reveal_others_sources(org: Org) -> None:
    src = source_id()
    create_lead(login_as(org.rep2.id), source_id=src)
    rep1 = login_as(org.rep1.id)
    assert rep1.get("/leads", params={"source_id": src}).json()["total"] == 0


def test_date_range_must_be_ordered(org: Org) -> None:
    response = login_as(org.rep1.id).get(
        "/leads", params={"created_from": "2026-02-01", "created_to": "2026-01-01"}
    )
    assert response.status_code == 422


def test_mutations_require_csrf(org: Org) -> None:
    client = login_as(org.rep1.id)
    del client.headers["X-CSRF-Token"]
    assert (
        client.post("/leads", json={"full_name": "علی رضایی", "mobile": "09121111111"}).status_code
        == 403
    )


# -- duplicates (spec 4.1, criterion 13) --------------------------------------


def test_duplicate_warning_and_explicit_override(org: Org) -> None:
    rep2 = login_as(org.rep2.id)
    rep2.post("/customers", json={"full_name": "مریم مرادی", "mobile": "09126666666"})
    rep1 = login_as(org.rep1.id)

    conflict = rep1.post("/leads", json={"full_name": "مریم", "mobile": "0912 666 6666"})
    assert conflict.status_code == 409
    [match] = conflict.json()["matches"]
    assert match["kind"] == "customer" and match["access"] == "limited"
    assert match["matched_on"] == ["mobile"]

    forced = rep1.post(
        "/leads", json={"full_name": "مریم", "mobile": "09126666666", "allow_duplicate": True}
    )
    assert forced.status_code == 201


def test_duplicate_check_endpoint(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    create_lead(rep1, email="Ali@Example.com", mobile=None)
    matches = rep1.get("/duplicates", params={"email": "ali@example.COM"}).json()
    assert [m["matched_on"] for m in matches] == [["email"]]


# -- lead status --------------------------------------------------------------


def test_disqualifying_requires_reason(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    lead = create_lead(rep1)
    assert rep1.patch(f"/leads/{lead['id']}", json={"status": "disqualified"}).status_code == 422
    ok = rep1.patch(
        f"/leads/{lead['id']}", json={"status": "disqualified", "disqualify_reason": "بودجه ندارد"}
    )
    assert ok.status_code == 200 and ok.json()["disqualify_reason"] == "بودجه ندارد"
    back = rep1.patch(f"/leads/{lead['id']}", json={"status": "working"})
    assert back.json()["disqualify_reason"] is None


# -- conversion (criterion 4) -------------------------------------------------


def _customer_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Customer)) or 0


def test_convert_to_new_customer_is_idempotent(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    lead = create_lead(rep1, company_name="شرکت آبان", source_id=source_id())

    first = rep1.post(f"/leads/{lead['id']}/convert", json={"job_title": "مدیر خرید"})
    assert first.status_code == 200 and first.json()["created_customer"] is True
    again = rep1.post(f"/leads/{lead['id']}/convert", json={})
    assert again.json()["customer_id"] == first.json()["customer_id"]
    assert again.json()["created_customer"] is False
    assert _customer_count() == 1

    customer = rep1.get(f"/customers/{first.json()['customer_id']}").json()
    assert customer["owner"]["id"] == str(org.rep1.id)
    assert customer["source"]["id"] == source_id()
    assert customer["organizations"][0]["organization"]["name"] == "شرکت آبان"
    assert customer["organizations"][0]["job_title"] == "مدیر خرید"
    lead_after = rep1.get(f"/leads/{lead['id']}").json()
    assert lead_after["status"] == "converted"
    assert rep1.patch(f"/leads/{lead['id']}", json={"full_name": "x y"}).status_code == 409


def test_concurrent_conversion_creates_one_customer(org: Org) -> None:
    lead = create_lead(login_as(org.rep1.id))
    clients = [login_as(org.rep1.id), login_as(org.rep1.id)]
    results: list[int] = []

    def convert(client: TestClient) -> None:
        results.append(client.post(f"/leads/{lead['id']}/convert", json={}).status_code)

    threads = [threading.Thread(target=convert, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200, 200]
    assert _customer_count() == 1


def test_convert_attaches_to_existing_customer(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    customer = rep1.post("/customers", json={"full_name": "علی رضایی", "mobile": "09121111111"})
    lead = create_lead(rep1, allow_duplicate=True)

    # Creating a second customer with the same number is flagged...
    assert rep1.post(f"/leads/{lead['id']}/convert", json={}).status_code == 409
    # ...and attaching to the existing one creates none.
    response = rep1.post(
        f"/leads/{lead['id']}/convert", json={"customer_id": customer.json()["id"]}
    )
    assert response.status_code == 200 and response.json()["created_customer"] is False
    assert _customer_count() == 1


def test_cannot_attach_lead_to_someone_elses_customer(org: Org) -> None:
    other = login_as(org.rep2.id).post(
        "/customers", json={"full_name": "مریم مرادی", "mobile": "09127777777"}
    )
    rep1 = login_as(org.rep1.id)
    lead = create_lead(rep1)
    response = rep1.post(f"/leads/{lead['id']}/convert", json={"customer_id": other.json()["id"]})
    assert response.status_code == 403


# -- archive --------------------------------------------------------------------


def test_archive_hides_record_and_manager_can_restore(org: Org) -> None:
    rep1, manager = login_as(org.rep1.id), login_as(org.manager.id)
    lead = create_lead(rep1)
    assert manager.post(f"/leads/{lead['id']}/archive").status_code == 200

    assert rep1.get("/leads").json()["total"] == 0
    assert rep1.get(f"/leads/{lead['id']}").status_code == 404
    assert rep1.get("/leads", params={"archived": True}).status_code == 403
    assert manager.get("/leads", params={"archived": True}).json()["total"] == 1

    assert manager.post(f"/leads/{lead['id']}/restore").status_code == 200
    assert rep1.get(f"/leads/{lead['id']}").json()["access"] == "full"


# -- customers & organizations --------------------------------------------------


def test_customer_needs_a_contact_and_links_organizations(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    assert rep1.post("/customers", json={"full_name": "علی رضایی"}).status_code == 422

    organization = rep1.post("/organizations", json={"name": "گروه سپهر"}).json()
    customer = rep1.post(
        "/customers",
        json={
            "full_name": "علی رضایی",
            "phone": "021-88888888",
            "organization_id": organization["id"],
            "job_title": "مدیرعامل",
        },
    )
    assert customer.status_code == 201
    second = rep1.post("/organizations", json={"name": "شرکت آریا"}).json()
    linked = rep1.post(
        f"/customers/{customer.json()['id']}/organizations",
        json={"organization_id": second["id"]},
    ).json()
    assert {o["organization"]["name"] for o in linked["organizations"]} == {
        "گروه سپهر",
        "شرکت آریا",
    }


def test_organization_members_respect_access(org: Org) -> None:
    organization = login_as(org.rep2.id).post("/organizations", json={"name": "گروه سپهر"}).json()
    login_as(org.rep2.id).post(
        "/customers",
        json={
            "full_name": "مریم مرادی",
            "mobile": "09128888888",
            "organization_id": organization["id"],
        },
    )
    detail = login_as(org.rep1.id).get(f"/organizations/{organization['id']}").json()
    [member] = detail["members"]
    assert member["customer"]["access"] == "limited"
    assert "mobile" not in member["customer"]


def test_assignable_users_follow_role(org: Org) -> None:
    def names(client: TestClient) -> set[str]:
        return {u["full_name"] for u in client.get("/users/assignable").json()}

    assert names(login_as(org.rep1.id)) == {"کارشناس ۱"}
    assert names(login_as(org.manager.id)) == {"مدیر الف", "کارشناس ۱", "کارشناس ۲"}
    assert len(names(login_as(org.admin.id))) == 6


def test_only_admin_manages_sources(org: Org) -> None:
    body = {"name": "نمایشگاه"}
    assert login_as(org.manager.id).post("/lead-sources", json=body).status_code == 403
    assert login_as(org.admin.id).post("/lead-sources", json=body).status_code == 201
    assert login_as(org.admin.id).post("/lead-sources", json=body).status_code == 409
