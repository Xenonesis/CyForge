import os
from pathlib import Path

test_db = Path(__file__).resolve().parents[1] / "test-cyberforge.db"
if test_db.exists():
    test_db.unlink()

os.environ.setdefault("CYBERFORGE_DATABASE_URL", f"sqlite+pysqlite:///{test_db.as_posix()}")
os.environ.setdefault("CYBERFORGE_REPOSITORY", "sqlalchemy")
os.environ.setdefault("CYBERFORGE_PROVISIONER", "mock")

from fastapi.testclient import TestClient

from cyberforge.main import app


def test_root_ui_and_system_info() -> None:
    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "Range Control Deck" in root.text
        assert "Dark Mode" in root.text

        info = client.get("/api/v1/system/info")
        assert info.status_code == 200
        payload = info.json()
        assert payload["repository_backend"] == "sqlalchemy"
        assert payload["provisioner_mode"] == "mock"

        summary = client.get("/api/v1/catalog/summary")
        assert summary.status_code == 200
        summary_payload = summary.json()
        assert summary_payload["content"]["independent"] == 15
        assert summary_payload["content"]["killchain"] == 5
        assert summary_payload["content"]["total"] == 20

        killchains = client.get("/api/v1/killchains")
        assert killchains.status_code == 200
        killchains_payload = killchains.json()
        assert len(killchains_payload) == 5
        assert all(item.get("content_type") == "killchain" for item in killchains_payload)

        abilities = client.get("/api/v1/caldera/abilities")
        assert abilities.status_code == 200
        abilities_payload = abilities.json()
        assert len(abilities_payload) == 40

        export_index = client.get("/api/v1/caldera/export/index")
        assert export_index.status_code == 200
        index_payload = export_index.json()
        assert index_payload["total"] == 40
        bundles = {bundle["name"]: bundle["count"] for bundle in index_payload["bundles"]}
        assert bundles["independent"] == 15
        assert bundles["killchain-scenarios"] == 5
        assert bundles["killchain-machines"] == 20

        independent_bundle = client.get("/api/v1/caldera/export/independent")
        assert independent_bundle.status_code == 200
        assert "id: cf-challenge-001-sqli" in independent_bundle.text

        scenarios_bundle = client.get("/api/v1/caldera/export/killchain-scenarios")
        assert scenarios_bundle.status_code == 200
        assert "id: cf-killchain-001-web-to-ad" in scenarios_bundle.text

        machines_bundle = client.get("/api/v1/caldera/export/killchain-machines")
        assert machines_bundle.status_code == 200
        assert "id: cf-killchain-001-web-to-ad-web01" in machines_bundle.text


def test_list_challenges_and_deploy_reset_flow() -> None:
    with TestClient(app) as client:
        list_response = client.get("/api/v1/challenges")
        assert list_response.status_code == 200
        challenges = list_response.json()
        assert len(challenges) == 20

        challenge_id = challenges[0]["id"]

        deploy_response = client.post(
            "/api/v1/labs/deploy",
            json={"user_id": "user-1", "challenge_id": challenge_id},
            headers={"X-Request-ID": "req-deploy-123"},
        )
        assert deploy_response.status_code == 200
        lab = deploy_response.json()
        assert lab["state"] == "active"
        assert deploy_response.headers.get("X-Request-ID") == "req-deploy-123"

        reset_response = client.post(
            f"/api/v1/labs/{lab['id']}/reset",
            headers={"X-Request-ID": "req-reset-456"},
        )
        assert reset_response.status_code == 200
        reset_lab = reset_response.json()
        assert reset_lab["state"] == "active"
        assert reset_response.headers.get("X-Request-ID") == "req-reset-456"

        events_response = client.get(
            "/api/v1/audit/events",
            params={"limit": 20, "action": "deploy", "status": "success", "request_id": "req-deploy-123"},
        )
        assert events_response.status_code == 200
        page = events_response.json()
        assert page["total"] >= 1
        assert page["items"]
        assert all(event["action"] == "deploy" for event in page["items"])
        assert all(event["status"] == "success" for event in page["items"])
        assert all(event["details"].get("request_id") == "req-deploy-123" for event in page["items"])


def test_audit_pagination_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/audit/events", params={"limit": 2, "offset": 0})
        assert response.status_code == 200
        payload = response.json()
        assert set(payload.keys()) == {"items", "total", "limit", "offset"}
        assert payload["limit"] == 2
        assert payload["offset"] == 0
