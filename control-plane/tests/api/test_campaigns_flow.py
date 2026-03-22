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


def test_get_schedule_config_returns_pure_json(client):
    campaign_id = _create_campaign(client)
    resp = client.get(f"/api/v1/campaigns/{campaign_id}/schedule-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "schedule_update"
    assert "playlist" in body
    assert isinstance(body["playlist"], list)
    assert "campaign_id" not in body


def test_gateway_device_schedule_returns_published_schedule_config(client, monkeypatch):
    campaign_id = _create_campaign(client)
    campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] = "published"

    monkeypatch.setattr(
        campaigns_ep.db_service,
        "get_latest_published_campaign_for_device",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    resp = client.get("/api/v1/gateway/devices/dev_001/schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "schedule_update"
    assert body["version"]
    assert "playlist" in body
    assert body["playlist"][0]["id"] == "ad_101"


def test_gateway_device_schedule_supports_edge_format(client, monkeypatch):
    campaign_id = _create_campaign(client)
    campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] = "published"

    monkeypatch.setattr(
        campaigns_ep.db_service,
        "get_latest_published_campaign_for_device",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    resp = client.get("/api/v1/gateway/devices/dev_001/schedule?format=edge-schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_id"].startswith("POL_SH_")
    assert "time_slots" in body
    assert body["time_slots"][-1]["slot_id"] == 99


def test_gateway_device_bundle_returns_schedule_and_assets(client, monkeypatch):
    campaign_id = _create_campaign(client)
    campaigns_ep._CAMPAIGN_STORE[campaign_id]["status"] = "published"

    monkeypatch.setattr(
        campaigns_ep.db_service,
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
    assert len(body["assets"]) == 1
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


def test_get_edge_schedule_returns_terminal_shape(client):
    campaign_id = _create_campaign(client)
    resp = client.get(f"/api/v1/campaigns/{campaign_id}/edge-schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_id"].startswith("POL_SH_")
    assert "effective_date" in body
    assert "download_base_url" in body
    assert "global_config" in body
    assert body["global_config"]["default_volume"] == 60
    assert body["global_config"]["download_retry_count"] == 3
    assert body["global_config"]["report_interval_sec"] == 60
    assert isinstance(body["interrupts"], list)
    assert isinstance(body["time_slots"], list)
    assert len(body["time_slots"]) == 3
    first = body["time_slots"][0]
    assert first["time_range"] == "08:00:00-10:00:00"
    assert first["loop_mode"] == "sequence"
    assert "ad_101" in first["playlist"]
    fallback = body["time_slots"][-1]
    assert fallback["slot_id"] == 99
    assert fallback["time_range"] == "00:00:00-23:59:59"
    assert fallback["loop_mode"] == "random"


def test_get_edge_schedule_contains_interrupts_from_time_rules(client):
    resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload_with_interrupts())
    assert resp.status_code == 200
    campaign_id = resp.json()["campaign_id"]

    edge = client.get(f"/api/v1/campaigns/{campaign_id}/edge-schedule")
    assert edge.status_code == 200
    body = edge.json()
    assert isinstance(body["interrupts"], list)
    assert len(body["interrupts"]) == 1
    item = body["interrupts"][0]
    assert item["trigger_type"] == "command"
    assert item["ad_id"] == "AD_EMERGENCY_FIRE"
    assert item["priority"] == 999
    assert item["play_mode"] == "loop_until_stop"


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


def test_publish_returns_400_on_validation_error(client, monkeypatch):
    campaign_id = _create_campaign(client)
    # Force invalid target devices to trigger validation failure.
    campaigns_ep._CAMPAIGN_STORE[campaign_id]["target_device_groups"] = []

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["message"] == "publish validation failed"
    assert "no target devices" in detail["errors"]


def test_publish_returns_502_when_gateway_delivery_fails(client, monkeypatch):
    campaign_id = _create_campaign(client)

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", lambda **kwargs: len(kwargs["results"]))
    monkeypatch.setattr(
        campaigns_ep,
        "send_remote_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("gateway down")),
    )

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["message"] == "gateway delivery failed"
    assert detail["batch_id"].startswith("pub_")
    assert len(detail["results"]) == 2


def test_publish_returns_503_when_db_down_and_fallback_disabled(client, monkeypatch):
    campaign_id = _create_campaign(client)
    settings.enable_memory_fallback = False
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "update_campaign_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "database unavailable"


def test_retry_failed_returns_503_when_log_query_fails(client, monkeypatch):
    campaign_id = _create_campaign(client)
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "get_latest_failed_campaign_devices",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/retry-failed")
    assert resp.status_code == 503
    assert "failed to query logs" in resp.json()["detail"]


def test_retry_failed_returns_502_when_gateway_delivery_fails(client, monkeypatch):
    campaign_id = _create_campaign(client)
    monkeypatch.setattr(campaigns_ep.db_service, "get_latest_failed_campaign_devices", lambda *_args, **_kwargs: ["dev_001"])
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "mark_campaign_retry_batch",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", lambda **kwargs: len(kwargs["results"]))
    monkeypatch.setattr(
        campaigns_ep,
        "send_remote_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("gateway down")),
    )

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/retry-failed")
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["message"] == "gateway retry delivery failed"
    assert detail["batch_id"].startswith("pub_")
    assert len(detail["results"]) == 1


def test_retry_failed_is_idempotent_by_source_batch(client, monkeypatch):
    campaign_id = _create_campaign(client)
    monkeypatch.setattr(
        campaigns_ep,
        "_latest_batch_for_campaign",
        lambda *_args, **_kwargs: {
            "campaign_id": campaign_id,
            "version": "20260308_v1",
            "batch_id": "pub_src1",
            "results": [{"device_id": "dev_001", "ok": False, "error": "timeout"}],
        },
    )
    monkeypatch.setattr(campaigns_ep.db_service, "get_latest_failed_campaign_devices", lambda *_args, **_kwargs: ["dev_001"])
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "mark_campaign_retry_batch",
        lambda *_args, **_kwargs: False,
    )

    resp = client.post(f"/api/v1/campaigns/{campaign_id}/retry-failed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["idempotent"] is True
    assert body["retried"] == 0
    assert body["message"] == "source batch already retried"


def test_campaign_full_chain_regression_flow(client, monkeypatch):
    logs = []
    batch_retried = set()

    def _insert_logs(**kwargs):
        batch_id = kwargs["batch_id"]
        campaign_id = kwargs["campaign_id"]
        version = kwargs["version"]
        for r in kwargs["results"]:
            logs.append(
                {
                    "campaign_id": campaign_id,
                    "batch_id": batch_id,
                    "version": version,
                    "device_id": r.get("device_id"),
                    "ok": bool(r.get("ok")),
                    "error": r.get("error"),
                    "created_at": "2026-03-08T00:00:00Z",
                }
            )
        return len(kwargs["results"])

    def _list_logs(campaign_id, limit=100, offset=0):
        rows = [r for r in logs if r["campaign_id"] == campaign_id]
        rows = list(reversed(rows))
        return rows[offset:offset + limit]

    def _failed_devices(campaign_id):
        if not logs:
            return []
        latest_batch = logs[-1]["batch_id"]
        return [r["device_id"] for r in logs if r["campaign_id"] == campaign_id and r["batch_id"] == latest_batch and r["ok"] is False]

    def _mark_retry(campaign_id, source_batch_id):
        key = (campaign_id, source_batch_id)
        if key in batch_retried:
            return False
        batch_retried.add(key)
        return True

    call_count = {"n": 0}

    def _send_remote_command(device_id, *_args, **_kwargs):
        call_count["n"] += 1
        # first publish: dev_002 fails once to produce retry target
        if call_count["n"] == 2 and device_id == "dev_002":
            raise RuntimeError("mock gateway timeout")

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", _insert_logs)
    monkeypatch.setattr(campaigns_ep.db_service, "list_campaign_publish_logs", _list_logs)
    monkeypatch.setattr(campaigns_ep.db_service, "get_latest_failed_campaign_devices", _failed_devices)
    monkeypatch.setattr(campaigns_ep.db_service, "mark_campaign_retry_batch", _mark_retry)
    monkeypatch.setattr(campaigns_ep, "send_remote_command", _send_remote_command)

    create_resp = client.post("/api/v1/campaigns/strategy", json=_strategy_payload_with_interrupts())
    assert create_resp.status_code == 200
    campaign_id = create_resp.json()["campaign_id"]

    edge_resp = client.get(f"/api/v1/campaigns/{campaign_id}/edge-schedule")
    assert edge_resp.status_code == 200
    assert edge_resp.json()["time_slots"][-1]["slot_id"] == 99

    pub_resp = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert pub_resp.status_code == 200
    assert pub_resp.json()["pushed"] == 1
    assert pub_resp.json()["total"] == 2

    log_resp = client.get(f"/api/v1/campaigns/{campaign_id}/publish-logs")
    assert log_resp.status_code == 200
    assert log_resp.json()["failed"] >= 1

    versions_resp = client.get(f"/api/v1/campaigns/{campaign_id}/versions")
    assert versions_resp.status_code == 200
    version = versions_resp.json()["items"][0]["version"]

    rollback_resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/rollback",
        json={"version": version, "publish_now": True},
    )
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["published"] is True

    retry_resp = client.post(f"/api/v1/campaigns/{campaign_id}/retry-failed")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["retried"] == 0
    assert retry_resp.json()["message"] == "no failed devices to retry"

    retry_again_resp = client.post(f"/api/v1/campaigns/{campaign_id}/retry-failed")
    assert retry_again_resp.status_code == 200
    assert retry_again_resp.json()["retried"] == 0


def test_publish_is_idempotent_after_success(client, monkeypatch):
    campaign_id = _create_campaign(client)

    call_count = {"n": 0}

    def _ok_send(*_args, **_kwargs):
        call_count["n"] += 1

    monkeypatch.setattr(campaigns_ep.db_service, "update_campaign_status", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", lambda **kwargs: len(kwargs["results"]))
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "list_campaign_publish_logs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(campaigns_ep, "send_remote_command", _ok_send)

    first = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert first.status_code == 200
    assert first.json().get("idempotent") in (None, False)

    second = client.post(f"/api/v1/campaigns/{campaign_id}/publish")
    assert second.status_code == 200
    body = second.json()
    assert body["idempotent"] is True
    assert body["message"] == "already published for current version and target devices"
    # Only the first publish should invoke gateway calls (2 devices).
    assert call_count["n"] == 2


def test_rollback_publish_now_is_idempotent_after_success(client, monkeypatch):
    campaign_id = _create_campaign(client)
    versions_resp = client.get(f"/api/v1/campaigns/{campaign_id}/versions")
    version = versions_resp.json()["items"][0]["version"]

    call_count = {"n": 0}

    def _ok_send(*_args, **_kwargs):
        call_count["n"] += 1

    monkeypatch.setattr(campaigns_ep.db_service, "get_campaign_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_device_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "get_existing_material_ids", lambda ids: ids)
    monkeypatch.setattr(campaigns_ep.db_service, "insert_campaign_publish_logs", lambda **kwargs: len(kwargs["results"]))
    monkeypatch.setattr(
        campaigns_ep.db_service,
        "list_campaign_publish_logs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(campaigns_ep, "send_remote_command", _ok_send)

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
    assert body["message"] == "rollback version already published to target devices"
    assert call_count["n"] == 2
