"""授权版本跨进程保留，旧请求及旧客户端不能恢复前任负责人的权限。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import followup, repo
from aimail.store.db import connect
from conftest import make_raw


def grant_client(conn):
    mailbox = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    pk, _ = store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    if pk is None:
        pk = conn.execute("SELECT id FROM message WHERE direction='in'").fetchone()[0]
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    app = create_app(
        conn,
        mailbox,
        require_oa_auth=True,
        followup_members=("a@example.test", "b@example.test"),
        outreach_import_token="test-integration-token",
    )
    return TestClient(app), tid


def grant(client, tid, owner, version, *, legacy=False):
    body = {"external_id": "mail_123", "thread_id": tid, "recipient": owner}
    if not legacy:
        body["assignment_version"] = version
    return client.post(
        f"/v{1 if legacy else 2}/followups/access",
        json=body,
        headers={"Authorization": "Bearer test-integration-token"},
    )


def test_versioned_grant_is_idempotent_and_rejects_stale_conflicting_and_legacy_requests(conn):
    client, tid = grant_client(conn)
    first = grant(client, tid, "a@example.test", 2)
    assert first.status_code == 200, first.text
    assert first.json()["assignment_version"] == 2
    assert grant(client, tid, "a@example.test", 2).json() == first.json()
    second = grant(client, tid, "b@example.test", 4)
    assert second.status_code == 200
    for version, legacy in [(2, False), (4, False), (None, True)]:
        rejected = grant(client, tid, "a@example.test", version, legacy=legacy)
        assert rejected.status_code == 409
        assert followup.get(conn, tid)["owner"] == "b@example.test"
    assert conn.execute("SELECT COUNT(*) FROM followup_event").fetchone()[0] == 2
    assert (
        client.get(
            f"/api/followups/{tid}",
            headers={"X-OA-User": "a", "X-OA-Email": "a@example.test"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/followups/{tid}",
            headers={"X-OA-User": "b", "X-OA-Email": "b@example.test"},
        ).status_code
        == 200
    )


def test_same_owner_new_assignment_version_still_fences_older_requests(conn):
    client, tid = grant_client(conn)
    assert grant(client, tid, "a@example.test", 2).status_code == 200
    assert grant(client, tid, "a@example.test", 6).json()["assignment_version"] == 6
    assert grant(client, tid, "b@example.test", 4).status_code == 409
    assert grant(client, tid, "a@example.test", 6).json()["version"] == 2
    assert conn.execute("SELECT COUNT(*) FROM followup_event").fetchone()[0] == 2


def test_legacy_owner_can_migrate_to_versioned_grants_and_restart_keeps_fence(tmp_path):
    path = tmp_path / "mail.sqlite3"
    conn = connect(path)
    client, tid = grant_client(conn)
    assert grant(client, tid, "a@example.test", None, legacy=True).status_code == 200
    assert grant(client, tid, "b@example.test", 4).status_code == 200
    client.close()
    conn.close()
    restarted = connect(path)
    client, new_tid = grant_client(restarted)
    assert new_tid == tid
    assert grant(client, tid, "a@example.test", 2).status_code == 409
    assert grant(client, tid, "a@example.test", None, legacy=True).status_code == 409
    assert grant(client, tid, "b@example.test", 4).json()["assignment_version"] == 4
    assert restarted.execute("SELECT COUNT(*) FROM followup_event").fetchone()[0] == 2
    client.close()
    restarted.close()


@pytest.mark.parametrize("version", [None, 0, -1, True, "2", 2.0])
def test_invalid_assignment_version_does_not_grant_access(conn, version):
    client, tid = grant_client(conn)
    assert grant(client, tid, "a@example.test", version).status_code == 422
    assert followup.get(conn, tid) is None


def test_user_note_cannot_impersonate_external_assignment_authority(conn):
    client, tid = grant_client(conn)
    followup.transfer(conn, tid, "b@example.test", "a@example.test", 0, {}, "leadsgen:mail_123")
    followup.decide(conn, tid, "a@example.test", 1, "accept")
    assert grant(client, tid, "b@example.test", 4).status_code == 409
    assert followup.get(conn, tid)["owner"] == "a@example.test"


@pytest.mark.parametrize("violation", ["token", "member", "mailbox", "account"])
def test_versioned_endpoint_preserves_integration_membership_and_thread_scope(conn, violation):
    client, tid = grant_client(conn)
    body = {
        "external_id": "mail_123",
        "thread_id": tid,
        "recipient": "a@example.test",
        "assignment_version": 2,
    }
    headers = {"Authorization": "Bearer test-integration-token"}
    expected = {"token": 401, "member": 422, "mailbox": 404, "account": 409}[violation]
    if violation == "token":
        headers = {"Authorization": "Bearer wrong"}
    elif violation == "member":
        body["recipient"] = "outsider@example.test"
    elif violation == "mailbox":
        private = repo.ensure_mailbox(conn, "a@example.test")
        pk, _ = store_raw(
            conn, private, make_raw(message_id="<private@example.test>"), "in", datetime.now(UTC)
        )
        body["thread_id"] = conn.execute(
            "SELECT thread_id FROM message WHERE id=?",
            (pk,),
        ).fetchone()[0]
    else:
        assert grant(client, tid, "b@example.test", 1).status_code == 200
        body["external_id"] = "different-account"
    response = client.post("/v2/followups/access", json=body, headers=headers)
    assert response.status_code == expected, response.text
    state = followup.get(conn, tid)
    if violation == "account":
        assert state["owner"] == "b@example.test"
    else:
        assert state is None
