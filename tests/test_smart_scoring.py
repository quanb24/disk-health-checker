"""End-to-end tests for SMART result interpretation and scoring.

Each test feeds smartctl JSON through interpret_smart() and verifies
the resulting CheckResult has the expected verdict, health_state,
score range, and finding codes.

Assertion strategy: test verdict/health_state/score/finding codes,
NOT summary or reasoning strings (those are presentation, not logic).
"""

from __future__ import annotations

import json
import pathlib
import pytest

from disk_health_checker.checks.smart import interpret_smart

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "smartctl"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _base_smart_json() -> dict:
    """Minimal valid ATA JSON with all counters at zero."""
    return {
        "smart_status": {"passed": True},
        "device": {"type": "sat"},
        "model_name": "TestDrive",
        "temperature": {"current": 35},
        "power_on_time": {"hours": 1000},
        "ata_smart_attributes": {
            "table": [
                {"id": 5, "name": "Reallocated_Sector_Ct", "raw": {"value": 0, "string": "0"}},
                {"id": 197, "name": "Current_Pending_Sector", "raw": {"value": 0, "string": "0"}},
                {"id": 198, "name": "Offline_Uncorrectable", "raw": {"value": 0, "string": "0"}},
                {"id": 199, "name": "UDMA_CRC_Error_Count", "raw": {"value": 0, "string": "0"}},
            ],
        },
    }


def _finding_codes(result) -> list[str]:
    """Extract finding codes from a CheckResult."""
    return [f["code"] for f in result.details.get("findings", [])]


# ── ATA Inline Tests ───────────────────────────────────────────────


class TestATAInline:
    """ATA tests using inline JSON data."""

    def test_healthy_drive_scores_high(self):
        result = interpret_smart(_base_smart_json())
        assert result.details["health_state"] == "HEALTHY"
        assert result.details["verdict"] == "PASS"
        assert result.details["confidence"] == "HIGH"
        assert 80 <= result.details["health_score"] <= 100
        assert _finding_codes(result) == []

    def test_pending_sectors_mark_failing(self):
        data = _base_smart_json()
        data["ata_smart_attributes"]["table"][1]["raw"] = {"value": 4, "string": "4"}
        result = interpret_smart(data)
        assert result.details["health_state"] == "FAILING"
        assert result.details["verdict"] == "FAIL"
        assert result.details["health_score"] < 80
        assert "ata.pending_sectors" in _finding_codes(result)

    def test_overall_failed_marks_failing(self):
        data = _base_smart_json()
        data["smart_status"]["passed"] = False
        result = interpret_smart(data)
        assert result.details["health_state"] == "FAILING"
        assert result.details["verdict"] == "FAIL"
        assert "ata.overall_failed" in _finding_codes(result)

    def test_reallocated_low_marks_warning(self):
        data = _base_smart_json()
        data["ata_smart_attributes"]["table"][0]["raw"] = {"value": 12, "string": "12"}
        result = interpret_smart(data)
        assert result.details["health_state"] == "WARNING"
        assert result.details["verdict"] == "WARNING"
        assert "ata.reallocated.low" in _finding_codes(result)

    def test_reallocated_high_marks_failing(self):
        data = _base_smart_json()
        data["ata_smart_attributes"]["table"][0]["raw"] = {"value": 200, "string": "200"}
        result = interpret_smart(data)
        assert result.details["health_state"] == "FAILING"
        assert result.details["verdict"] == "FAIL"
        assert "ata.reallocated.high" in _finding_codes(result)

    def test_offline_uncorrectable_marks_failing(self):
        data = _base_smart_json()
        data["ata_smart_attributes"]["table"][2]["raw"] = {"value": 3, "string": "3"}
        result = interpret_smart(data)
        assert result.details["health_state"] == "FAILING"
        assert "ata.offline_uncorrectable" in _finding_codes(result)

    def test_elevated_temperature_marks_warning(self):
        data = _base_smart_json()
        data["temperature"]["current"] = 58
        result = interpret_smart(data)
        assert result.details["health_state"] == "WARNING"
        assert "ata.temperature.elevated" in _finding_codes(result)

    def test_very_high_temperature_marks_warning(self):
        data = _base_smart_json()
        data["temperature"]["current"] = 68
        result = interpret_smart(data)
        assert result.details["health_state"] == "WARNING"
        assert "ata.temperature.very_high" in _finding_codes(result)

    def test_udma_crc_errors_marks_warning(self):
        data = _base_smart_json()
        data["ata_smart_attributes"]["table"][3]["raw"] = {"value": 100, "string": "100"}
        result = interpret_smart(data)
        assert result.details["health_state"] == "WARNING"
        assert "ata.udma_crc_errors" in _finding_codes(result)

    def test_no_attributes_with_overall_passed_yields_unknown(self):
        """Empty attribute table with overall_passed=True → UNKNOWN.

        Even though overall_passed is present, missing attribute counters
        prevent a reliable assessment.  USB bridges commonly return
        overall_passed=True while stripping all attribute data.
        """
        data = {
            "smart_status": {"passed": True},
            "device": {"type": "sat"},
            "model_name": "BareDrive",
            "ata_smart_attributes": {"table": []},
        }
        result = interpret_smart(data)
        assert result.details["verdict"] == "UNKNOWN"
        assert result.details["confidence"] == "MEDIUM"
        assert result.details["health_state"] == "UNKNOWN"
        assert len(result.details["evidence_missing"]) > 0
        codes = _finding_codes(result)
        assert "smart.data_unavailable" in codes

    def test_no_attributes_no_overall_yields_unknown(self):
        """No attribute table AND no overall_passed → LOW confidence → UNKNOWN."""
        data = {
            "device": {"type": "sat"},
            "model_name": "BareDrive",
            "ata_smart_attributes": {"table": []},
        }
        result = interpret_smart(data)
        assert result.details["health_state"] == "UNKNOWN"
        assert result.details["verdict"] == "UNKNOWN"
        assert result.details["confidence"] == "LOW"
        assert len(result.details["evidence_missing"]) > 0

    def test_missing_overall_passed_medium_confidence(self):
        """Has counters but no overall_passed → MEDIUM confidence, still PASS."""
        data = _base_smart_json()
        del data["smart_status"]
        result = interpret_smart(data)
        assert result.details["confidence"] == "MEDIUM"
        assert result.details["verdict"] == "PASS"

    def test_multiple_warnings_combined(self):
        data = _base_smart_json()
        # Reallocated low + elevated temp + UDMA CRC
        data["ata_smart_attributes"]["table"][0]["raw"] = {"value": 5, "string": "5"}
        data["temperature"]["current"] = 57
        data["ata_smart_attributes"]["table"][3]["raw"] = {"value": 50, "string": "50"}
        result = interpret_smart(data)
        assert result.details["verdict"] == "WARNING"
        codes = _finding_codes(result)
        assert "ata.reallocated.low" in codes
        assert "ata.temperature.elevated" in codes
        assert "ata.udma_crc_errors" in codes
        assert result.details["health_score"] < 70


# ── ATA Fixture-Driven Tests ──────────────────────────────────────


class TestATAFixtures:
    """ATA tests using fixture files."""

    def test_ata_healthy_fixture(self):
        data = _load_fixture("ata_healthy.synthetic.json")
        result = interpret_smart(data)
        assert result.details["health_state"] == "HEALTHY"
        assert result.details["verdict"] == "PASS"
        assert result.details["confidence"] == "HIGH"
        assert 90 <= result.details["health_score"] <= 100
        assert _finding_codes(result) == []
        assert result.details["model_name"] == "WDC WD20EFRX-68EUZN0"

    def test_ata_failing_fixture(self):
        data = _load_fixture("ata_failing.synthetic.json")
        result = interpret_smart(data)
        assert result.details["health_state"] == "FAILING"
        assert result.details["verdict"] == "FAIL"
        codes = _finding_codes(result)
        assert "ata.overall_failed" in codes
        assert "ata.pending_sectors" in codes
        assert "ata.reallocated.high" in codes
        assert result.details["health_score"] < 30

    def test_ata_warning_fixture(self):
        data = _load_fixture("ata_warning.synthetic.json")
        result = interpret_smart(data)
        assert result.details["verdict"] in ("WARNING", "FAIL")
        codes = _finding_codes(result)
        assert "ata.reallocated.low" in codes
        assert "ata.temperature.elevated" in codes

    def test_ata_udma_crc_fixture(self):
        data = _load_fixture("ata_udma_crc.synthetic.json")
        result = interpret_smart(data)
        assert result.details["health_state"] == "WARNING"
        assert result.details["verdict"] == "WARNING"
        assert "ata.udma_crc_errors" in _finding_codes(result)
        # Should NOT be FAIL — CRC errors are cable issue, not media failure
        assert result.details["health_score"] >= 80

    def test_usb_blocked_no_attrs_fixture(self):
        """USB bridge returns identity but no attributes → UNKNOWN."""
        data = _load_fixture("usb_blocked_no_attrs.synthetic.json")
        result = interpret_smart(data)
        assert result.details["verdict"] == "UNKNOWN"
        assert result.details["health_state"] == "UNKNOWN"
        # overall_passed=True present → MEDIUM confidence, but still UNKNOWN verdict
        assert result.details["confidence"] == "MEDIUM"
        assert "smart.data_unavailable" in _finding_codes(result)


# ── NVMe Fixture-Driven Tests ─────────────────────────────────────


class TestNVMeFixtures:
    """NVMe tests using fixture files."""

    def test_nvme_healthy_fixture(self):
        data = _load_fixture("nvme_healthy.synthetic.json")
        result = interpret_smart(data)
        assert result.details["health_state"] == "HEALTHY"
        assert result.details["verdict"] == "PASS"
        assert 90 <= result.details["health_score"] <= 100
        assert result.details["model_name"] == "Samsung SSD 980 PRO 1TB"

    def test_nvme_wear_warning_fixture(self):
        data = _load_fixture("nvme_wear_warning.synthetic.json")
        result = interpret_smart(data)
        assert result.details["verdict"] in ("WARNING", "FAIL")
        codes = _finding_codes(result)
        # Should have wear-related findings
        wear_codes = [c for c in codes if "wear" in c or "spare" in c]
        assert len(wear_codes) > 0

    def test_nvme_critical_fixture(self):
        data = _load_fixture("nvme_critical_warning.synthetic.json")
        result = interpret_smart(data)
        assert result.details["health_state"] == "FAILING"
        assert result.details["verdict"] == "FAIL"
        assert result.details["health_score"] < 50
        codes = _finding_codes(result)
        assert len(codes) >= 3  # Multiple critical findings expected


# ── Schema Consistency Tests ──────────────────────────────────────


class TestSchemaConsistency:
    """Verify CheckResult.details always has the required schema fields."""

    REQUIRED_KEYS = {"verdict", "confidence", "health_score", "findings", "evidence_missing"}

    def test_healthy_ata_has_required_fields(self):
        result = interpret_smart(_base_smart_json())
        assert self.REQUIRED_KEYS.issubset(result.details.keys())

    def test_failing_ata_has_required_fields(self):
        data = _load_fixture("ata_failing.synthetic.json")
        result = interpret_smart(data)
        assert self.REQUIRED_KEYS.issubset(result.details.keys())

    def test_nvme_has_required_fields(self):
        data = _load_fixture("nvme_healthy.synthetic.json")
        result = interpret_smart(data)
        assert self.REQUIRED_KEYS.issubset(result.details.keys())

    def test_findings_are_well_formed(self):
        data = _load_fixture("ata_failing.synthetic.json")
        result = interpret_smart(data)
        for f in result.details["findings"]:
            assert "code" in f
            assert "severity" in f
            assert "message" in f
            assert "evidence" in f
