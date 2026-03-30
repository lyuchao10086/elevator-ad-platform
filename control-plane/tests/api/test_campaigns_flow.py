from app.api.v1.endpoints import campaigns as campaigns_ep
from app.api.v1.endpoints import gateway as gateway_ep
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


def _strategy_payload_with_interrupts() -> dict:
    payload = _strategy_payload()
    payload["time_rules"]["interrupts"] = [
        {
            "trigger_type": "command",
            "ad_id": "AD_EMERGENCY_FIRE",
            "priority": 999,
            "play_mode": "loop_until_stop",
        }
    ]
    return payload


def _create_campaign(client) -> str:
    resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload())
    assert resp.status_code == 200
    return resp.json()["campaign_id"]


def _publish_campaign(client, monkeypatch, campaign_id: str):
    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    return client.post(f"/api/v1/campaigns/{campaign_id}/publish")


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


def test_get_schedule_config_returns_pure_json(client):
    campaign_id = _create_campaign(client)

    resp = client.get(f"/api/v1/campaigns/{campaign_id}/schedule-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "schedule_update"
    assert isinstance(body["playlist"], list)
    assert "campaign_id" not in body


def test_get_edge_schedule_returns_terminal_shape(client):
    campaign_id = _create_campaign(client)

    resp = client.get(f"/api/v1/campaigns/{campaign_id}/edge-schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_id"].startswith("POL_SH_")
    assert body["global_config"]["default_volume"] == 60
    assert body["global_config"]["download_retry_count"] == 3
    assert body["global_config"]["report_interval_sec"] == 60
    assert body["time_slots"][0]["time_range"] == "08:00:00-10:00:00"
    assert body["time_slots"][-1]["slot_id"] == 99
    assert body["time_slots"][-1]["loop_mode"] == "random"


def test_get_edge_schedule_contains_interrupts_from_time_rules(client):
    resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload_with_interrupts())
    assert resp.status_code == 200
    campaign_id = resp.json()["campaign_id"]

    edge = client.get(f"/api/v1/campaigns/{campaign_id}/edge-schedule")
    assert edge.status_code == 200
    body = edge.json()
    assert len(body["interrupts"]) == 1
    assert body["interrupts"][0]["trigger_type"] == "command"
    assert body["interrupts"][0]["ad_id"] == "AD_EMERGENCY_FIRE"


def test_publish_marks_campaign_published_in_pull_mode(client, monkeypatch):
    campaign_id = _create_campaign(client)

    resp = _publish_campaign(client, monkeypatch, campaign_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["published"] is True
    assert body["delivery_mode"] == "pull"
    assert body["device_count"] == 2
    assert body["material_count"] == 1
    assert body["updated"] == 1
    assert "pushed" not in body
    assert campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] == "published"


def test_publish_returns_400_on_validation_error(client):
    campaign_id = _create_campaign(client)
    campaigns_ep._CAMPAIGN_STORE[campaign_id]["target_device_groups"] = []

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["message"] == "publish validation failed"
    assert "no target devices" in detail["errors"]
    assert campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] == "draft"


def test_publish_returns_503_when_db_down_and_fallback_disabled(client, monkeypatch):
    campaign_id = _create_campaign(client)
    settings.enable_memory_fallback = False
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "get_campaign",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "database unavailable"


def test_publish_is_idempotent_in_pull_mode(client, monkeypatch):
    campaign_id = _create_campaign(client)

    first = _publish_campaign(client, monkeypatch, campaign_id)
    assert first.status_code == 200
    assert first.json().get("idempotent") in (None, False)

    second = _publish_campaign(client, monkeypatch, campaign_id)
    assert second.status_code == 200
    body = second.json()
    assert body["idempotent"] is True
    assert body["updated"] == 0
    assert body["message"] == "already published in pull delivery mode"


def test_publish_logs_returns_empty_in_pull_mode(client):
    campaign_id = _create_campaign(client)

    resp = client.get(f"/api/v1/campaigns/{campaign_id}/publish-logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivery_mode"] == "pull"
    assert body["deprecated"] is True
    assert body["total"] == 0
    assert body["items"] == []


def test_retry_failed_returns_noop_in_pull_mode(client):
    campaign_id = _create_campaign(client)

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/retry-failed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivery_mode"] == "pull"
    assert body["deprecated"] is True
    assert body["retried"] == 0


def test_rollback_publish_now_marks_campaign_published_in_pull_mode(client, monkeypatch):
    campaign_id = _create_campaign(client)
    versions_resp = client.get(f"/api/v1/campaigns/{campaign_id}/versions")
    version = versions_resp.json()["items"][0]["version"]

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)

    resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/rollback",
        json={"version": version, "publish_now": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["published"] is True
    assert body["delivery_mode"] == "pull"
    assert body["version"] == version
    assert campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] == "published"


def test_rollback_without_publish_now_stays_draft_and_not_visible_to_gateway(client, monkeypatch):
    campaign_id = _create_campaign(client)
    _publish_campaign(client, monkeypatch, campaign_id)
    versions_resp = client.get(f"/api/v1/campaigns/{campaign_id}/versions")
    version = versions_resp.json()["items"][0]["version"]

    resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/rollback",
        json={"version": version, "publish_now": False},
    )
    assert resp.status_code == 200
    assert resp.json()["published"] is False
    assert resp.json()["delivery_mode"] == "pull"
    assert campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] == "draft"

    monkeypatch.setattr(
        gateway_ep.db_service,
        "get_latest_published_campaign_for_device",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    schedule_resp = client.get("/api/v1/gateway/devices/dev_001/schedule")
    assert schedule_resp.status_code == 404


def test_rollback_publish_now_is_idempotent_in_pull_mode(client, monkeypatch):
    campaign_id = _create_campaign(client)
    versions_resp = client.get(f"/api/v1/campaigns/{campaign_id}/versions")
    version = versions_resp.json()["items"][0]["version"]

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)

    first = client.post(
        f"/api/v1/campaigns/{campaign_id}/rollback",
        json={"version": version, "publish_now": True},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/campaigns/{campaign_id}/rollback",
        json={"version": version, "publish_now": True},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["idempotent"] is True
    assert body["updated"] == 0
    assert body["message"] == "rollback version already published in pull delivery mode"


def test_gateway_device_schedule_returns_published_schedule_config(client, monkeypatch):
    campaign_id = _create_campaign(client)
    publish_resp = _publish_campaign(client, monkeypatch, campaign_id)
    assert publish_resp.status_code == 200

    monkeypatch.setattr(
        gateway_ep.db_service,
        "get_latest_published_campaign_for_device",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    resp = client.get("/api/v1/gateway/devices/dev_001/schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "schedule_update"
    assert body["playlist"][0]["id"] == "ad_101"


def test_gateway_device_schedule_supports_edge_format(client, monkeypatch):
    campaign_id = _create_campaign(client)
    publish_resp = _publish_campaign(client, monkeypatch, campaign_id)
    assert publish_resp.status_code == 200

    monkeypatch.setattr(
        gateway_ep.db_service,
        "get_latest_published_campaign_for_device",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    resp = client.get("/api/v1/gateway/devices/dev_001/schedule?format=edge-schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_id"].startswith("POL_SH_")
    assert body["time_slots"][-1]["slot_id"] == 99


def test_gateway_device_bundle_returns_schedule_and_assets(client, monkeypatch):
    campaign_id = _create_campaign(client)
    publish_resp = _publish_campaign(client, monkeypatch, campaign_id)
    assert publish_resp.status_code == 200

    monkeypatch.setattr(
        gateway_ep.db_service,
        "get_latest_published_campaign_for_device",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        gateway_ep.db_service,
        "list_materials",
        lambda **_kwargs: [
            {
                "material_id": "mat_001",
                "ad_id": "ad_101",
                "file_name": "coke_cny.mp4",
                "md5": "a1b2c3",
                "type": "video",
                "duration_sec": 15,
                "size_bytes": 2048,
                "status": "ready",
            }
        ],
        raising=False,
    )

    resp = client.get("/api/v1/gateway/devices/dev_001/bundle")
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_id"] == "dev_001"
    assert body["schedule"]["type"] == "schedule_update"
    assert body["schedule_config"]["type"] == "schedule_update"
    assert body["edge_schedule"]["policy_id"].startswith("POL_SH_")
    assert body["assets"][0]["material_id"] == "mat_001"
    assert body["assets"][0]["download_url"].endswith("/api/v1/gateway/materials/mat_001/file")
    assert body["assets"][0]["source_url"].endswith("/coke_cny.mp4")


def test_gateway_material_metadata_by_ad_id_returns_download_url(client, monkeypatch):
    monkeypatch.setattr(
        gateway_ep.db_service,
        "list_materials",
        lambda **_kwargs: [
            {
                "material_id": "mat_001",
                "ad_id": "ad_101",
                "file_name": "coke_cny.mp4",
                "md5": "a1b2c3",
                "type": "video",
                "duration_sec": 15,
                "size_bytes": 2048,
                "status": "ready",
            }
        ],
        raising=False,
    )

    resp = client.get("/api/v1/gateway/materials/by-ad/ad_101")
    assert resp.status_code == 200
    body = resp.json()
    assert body["material_id"] == "mat_001"
    assert body["ad_id"] == "ad_101"
    assert body["download_url"].endswith("/api/v1/gateway/materials/mat_001/file")
