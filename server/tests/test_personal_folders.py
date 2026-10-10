"""Private folder scopes, three levels and originals/workflow preservation."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import repo
from conftest import make_raw


def test_folder_tree_ownership_depth_move_and_safe_delete(conn, mailbox):
    pk, _ = store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    with TestClient(create_app(conn, mailbox)) as client:
        alice, bob = {"X-User": "Alice"}, {"X-User": "Bob"}
        assert client.get("/api/folders").status_code == 401

        def create(name, parent=None, headers=alice):
            return client.post(
                "/api/folders", headers=headers, json={"name": name, "parent_id": parent}
            )

        root = create("客户").json()["items"][0]["id"]
        child = next(f["id"] for f in create("亚洲", root).json()["items"] if f["name"] == "亚洲")
        leaf = next(
            f["id"] for f in create("新加坡", child).json()["items"] if f["name"] == "新加坡"
        )
        assert create("第四层", leaf).status_code == 422
        assert create("客户").status_code == 409
        assert create("客户", headers=bob).status_code == 200
        assert create("越权", root, bob).status_code == 404
        assert len(client.get("/api/folders", headers=bob).json()["items"]) == 1
        assert (
            client.patch(f"/api/folders/{leaf}", headers=bob, json={"name": "改名"}).status_code
            == 404
        )
        assert client.delete(f"/api/folders/{root}", headers=alice).status_code == 409
        assert (
            client.put(
                f"/api/threads/{tid}/folder", headers=bob, json={"folder_id": leaf}
            ).status_code
            == 404
        )
        moved = client.put(
            f"/api/threads/{tid}/folder", headers=alice, json={"folder_id": leaf}
        ).json()
        assert moved["assignments"] == {str(tid): leaf}
        assert next(f["count"] for f in moved["items"] if f["id"] == leaf) == 1
        assert client.get("/api/folders", headers=bob).json()["assignments"] == {}
        assert client.delete(f"/api/folders/{leaf}", headers=alice).status_code == 409
        assert (
            client.put(
                f"/api/threads/{tid}/folder", headers=alice, json={"folder_id": None}
            ).status_code
            == 200
        )
        assert client.delete(f"/api/folders/{leaf}", headers=alice).status_code == 200
    row = conn.execute("SELECT raw FROM message WHERE id=?", (pk,)).fetchone()
    assert bytes(row[0]) == make_raw()
    assert conn.execute("SELECT folder FROM thread WHERE id=?", (tid,)).fetchone()[0] == "inbox"


def test_folders_use_stable_trusted_identity_and_mailbox_access(conn, mailbox):
    other = repo.ensure_mailbox(conn, "private@example.test", "Private")
    with TestClient(
        create_app(
            conn,
            mailbox,
            require_oa_auth=True,
            mailbox_access={
                "alice@example.test": ("sales@example.test", "private@example.test"),
                "bob@example.test": ("sales@example.test",),
            },
        )
    ) as client:
        alice = {"X-OA-User": "Alice", "X-OA-Email": "alice@example.test"}
        root = client.post("/api/folders", headers=alice, json={"name": "采购"}).json()["items"][0][
            "id"
        ]
        changed_name = {**alice, "X-OA-User": "New name", "X-User": "Bob"}
        assert client.get("/api/folders", headers=changed_name).json()["items"][0]["id"] == root
        private = {**alice, "X-Mailbox-Address": "private@example.test"}
        assert client.get("/api/folders", headers=private).json()["items"] == []
        assert (
            client.post(
                "/api/folders", headers=private, json={"name": "跨邮箱", "parent_id": root}
            ).status_code
            == 404
        )
        bob = {"X-OA-User": "Alice", "X-OA-Email": "bob@example.test"}
        assert client.get("/api/folders", headers=bob).json()["items"] == []
        assert (
            client.get(
                "/api/folders", headers={**bob, "X-Mailbox-Address": "private@example.test"}
            ).status_code
            == 403
        )
        assert client.get("/api/folders", headers={"X-User": "Alice"}).status_code in {401, 403}
    assert other != mailbox
