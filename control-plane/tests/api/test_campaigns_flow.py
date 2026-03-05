from app.api.v1.endpoints import campaigns as campaigns_ep
from app.core.config import settings


def _strategy_payload() -> dict:
    return {
        "ads_list": [
            {
                "id": "ad_101",
                "file": "coke_cny.mp4",
                "md5": "a1b2c3",
                "priority": 10,
                "slots": ["08:00-10:00", "17:00-19:00"],
            }
        ],
        "devices_list": ["dev_001", "dev_002"],
        "time_rules": {"name": "morning_campaign", "creator_id": "u_1"},
        "download_base_url": "https://oss.aliyun.com/ads/",
    }


def _create_campaign(client) -> str:
    resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload())
    assert resp.status_code == 200
    return resp.json()["campaign_id"]


def test_strategy_uses_memory_fallback_when_db_down(client, monkeypatch):
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "insert_campaign",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["campaign_status"] == "draft"
    assert body["persisted"] is False

    list_resp = client.get("/api/v1/campaigns/")
    assert list_resp.status_code == 200
    ids = [item["campaign_id"] for item in list_resp.json()["items"]]
    assert body["campaign_id"] in ids


def test_strategy_returns_503_when_db_down_and_fallback_disabled(client, monkeypatch):
    settings.enable_memory_fallback = False
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "insert_campaign",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload())
    assert resp.status_code == 503
    assert resp.json()["detail"] == "database unavailable"


def test_publish_campaign_success(client, monkeypatch):
    campaign_id = _create_campaign(client)

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", lambda **kwargs: len(kwargs["results"]))
    monkeypatch.setattr(campaigns_ep, "send_remote_command", lambda *_args, **_kwargs: None)

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["pushed"] == 2
    assert body["total"] == 2
    assert body["persisted_logs"] == 2


def test_rollback_publish_now_success(client, monkeypatch):
    campaign_id = _create_campaign(client)
    versions_resp = client.get(f"/api/v1/campaigns/{campaign_id}/versions")
    assert versions_resp.status_code == 200
    version = versions_resp.json()["items"][0]["version"]

    monkeypatch.setattr(campaigns_ep.db_service, "get_campaign_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", lambda **kwargs: len(kwargs["results"]))
    monkeypatch.setattr(campaigns_ep, "send_remote_command", lambda *_args, **_kwargs: None)

    resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/rollback",
        json={"version": version, "publish_now": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["published"] is True
    assert body["version"] == version
