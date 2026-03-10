from __future__ import annotations

from disk_health_checker.checks.smart import interpret_smart


def _base_smart_json() -> dict:
    return {
        "smart_status": {"passed": True},
        "ata_smart_attributes": {
            "table": [],
        },
        "device": {"model_name": "TestDrive"},
    }


def test_healthy_drive_scores_high():
    data = _base_smart_json()
    result = interpret_smart(data)
    assert result.details["health_state"] == "HEALTHY"
    assert 80 <= result.details["health_score"] <= 100


def test_pending_sectors_mark_failing():
    data = _base_smart_json()
    data["ata_smart_attributes"]["table"] = [
        {"name": "Current_Pending_Sector", "raw": {"value": 4}},
    ]
    result = interpret_smart(data)
    assert result.details["health_state"] == "FAILING"
    assert result.details["health_score"] < 80


