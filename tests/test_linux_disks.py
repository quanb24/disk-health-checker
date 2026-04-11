"""Tests for Linux disk enumeration via lsblk."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from disk_health_checker.utils.disks import (
    DiskInfo,
    _list_disks_linux,
    _enrich_linux_mounts,
)


# ── Fixtures: realistic lsblk JSON outputs ──────────────────────────

LSBLK_NODEPS_BASIC = {
    "blockdevices": [
        {
            "name": "sda",
            "size": 500107862016,
            "model": "Samsung SSD 860",
            "tran": "sata",
            "type": "disk",
            "mountpoint": None,
            "rm": False,
            "ro": False,
        },
        {
            "name": "nvme0n1",
            "size": 1000204886016,
            "model": "WD Black SN770",
            "tran": "nvme",
            "type": "disk",
            "mountpoint": None,
            "rm": False,
            "ro": False,
        },
    ]
}

LSBLK_NODEPS_USB = {
    "blockdevices": [
        {
            "name": "sdb",
            "size": 2000398934016,
            "model": "My Passport 25E2",
            "tran": "usb",
            "type": "disk",
            "mountpoint": None,
            "rm": True,
            "ro": False,
        },
    ]
}

LSBLK_NODEPS_EMPTY = {"blockdevices": []}

LSBLK_NODEPS_MIXED_TYPES = {
    "blockdevices": [
        {
            "name": "sda",
            "size": 500107862016,
            "model": "Samsung SSD 860",
            "tran": "sata",
            "type": "disk",
            "mountpoint": None,
            "rm": False,
            "ro": False,
        },
        {
            "name": "loop0",
            "size": 109051904,
            "model": None,
            "tran": None,
            "type": "loop",
            "mountpoint": "/snap/core/12345",
            "rm": False,
            "ro": True,
        },
    ]
}

# Second lsblk call (with children) for mount enrichment
LSBLK_TREE_WITH_MOUNTS = {
    "blockdevices": [
        {
            "name": "sda",
            "mountpoint": None,
            "pkname": None,
            "children": [
                {"name": "sda1", "mountpoint": "/boot/efi", "pkname": "sda"},
                {"name": "sda2", "mountpoint": "/", "pkname": "sda"},
                {"name": "sda3", "mountpoint": "/home", "pkname": "sda"},
            ],
        },
        {
            "name": "nvme0n1",
            "mountpoint": None,
            "pkname": None,
            "children": [
                {"name": "nvme0n1p1", "mountpoint": "/mnt/data", "pkname": "nvme0n1"},
            ],
        },
    ]
}

LSBLK_TREE_EMPTY = {"blockdevices": []}


# ── Helpers ──────────────────────────────────────────────────────────

def _make_run_side_effect(nodeps_data, tree_data=None):
    """Return a side_effect function that returns different data for
    the --nodeps call vs the tree call."""
    tree_data = tree_data or LSBLK_TREE_EMPTY

    def side_effect(cmd, **kwargs):
        stdout = ""
        if "--nodeps" in cmd:
            stdout = json.dumps(nodeps_data)
        else:
            stdout = json.dumps(tree_data)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=stdout, stderr=""
        )

    return side_effect


def _make_linux_platform():
    """Patch get_platform_info to return Linux."""
    from disk_health_checker.utils.platform import PlatformInfo
    return PlatformInfo(system="Linux", release="6.1.0", is_linux=True, is_macos=False)


# ── Tests ────────────────────────────────────────────────────────────


class TestListDisksLinuxBasic:
    """Core enumeration from lsblk --nodeps output."""

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_sata_and_nvme(self, mock_run, _mock_platform):
        mock_run.side_effect = _make_run_side_effect(
            LSBLK_NODEPS_BASIC, LSBLK_TREE_WITH_MOUNTS
        )
        disks = _list_disks_linux()
        assert len(disks) == 2

        sda = disks[0]
        assert sda.identifier == "sda"
        assert sda.device_node == "/dev/sda"
        assert sda.size_bytes == 500107862016
        assert sda.model == "Samsung SSD 860"
        assert sda.protocol == "SATA"
        assert sda.is_internal is True
        assert sda.is_external is False
        assert sda.is_virtual is False

        nvme = disks[1]
        assert nvme.identifier == "nvme0n1"
        assert nvme.device_node == "/dev/nvme0n1"
        assert nvme.protocol == "NVME"
        assert nvme.size_bytes == 1000204886016

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_usb_removable(self, mock_run, _mock_platform):
        mock_run.side_effect = _make_run_side_effect(LSBLK_NODEPS_USB)
        disks = _list_disks_linux()
        assert len(disks) == 1
        assert disks[0].is_external is True
        assert disks[0].is_internal is False
        assert disks[0].protocol == "USB"

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_filters_non_disk_types(self, mock_run, _mock_platform):
        mock_run.side_effect = _make_run_side_effect(LSBLK_NODEPS_MIXED_TYPES)
        disks = _list_disks_linux()
        assert len(disks) == 1
        assert disks[0].identifier == "sda"

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_empty_blockdevices(self, mock_run, _mock_platform):
        mock_run.side_effect = _make_run_side_effect(LSBLK_NODEPS_EMPTY)
        disks = _list_disks_linux()
        assert disks == []


class TestListDisksLinuxMountEnrichment:
    """Mount points from child partitions are collected."""

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_mounts_from_partitions(self, mock_run, _mock_platform):
        mock_run.side_effect = _make_run_side_effect(
            LSBLK_NODEPS_BASIC, LSBLK_TREE_WITH_MOUNTS
        )
        disks = _list_disks_linux()
        sda = disks[0]
        assert "/boot/efi" in sda.mount_points
        assert "/" in sda.mount_points
        assert "/home" in sda.mount_points

        nvme = disks[1]
        assert "/mnt/data" in nvme.mount_points


class TestListDisksLinuxErrorHandling:
    """Graceful degradation when lsblk is unavailable or misbehaves."""

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run", side_effect=FileNotFoundError)
    def test_lsblk_not_found(self, mock_run, _mock_platform):
        disks = _list_disks_linux()
        assert disks == []

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch(
        "disk_health_checker.utils.disks.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "lsblk"),
    )
    def test_lsblk_nonzero_exit(self, mock_run, _mock_platform):
        disks = _list_disks_linux()
        assert disks == []

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch(
        "disk_health_checker.utils.disks.subprocess.run",
        side_effect=subprocess.TimeoutExpired("lsblk", 15),
    )
    def test_lsblk_timeout(self, mock_run, _mock_platform):
        disks = _list_disks_linux()
        assert disks == []

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_lsblk_invalid_json(self, mock_run, _mock_platform):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["lsblk"], returncode=0, stdout="not json at all", stderr=""
        )
        disks = _list_disks_linux()
        assert disks == []


class TestListDisksLinuxEdgeCases:
    """Edge cases in lsblk data."""

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_size_as_string(self, mock_run, _mock_platform):
        """Some lsblk versions return size as a string."""
        data = {
            "blockdevices": [
                {
                    "name": "sda",
                    "size": "500107862016",
                    "model": "Test Drive",
                    "tran": "sata",
                    "type": "disk",
                    "mountpoint": None,
                    "rm": False,
                    "ro": False,
                }
            ]
        }
        mock_run.side_effect = _make_run_side_effect(data)
        disks = _list_disks_linux()
        assert disks[0].size_bytes == 500107862016

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_null_model_and_tran(self, mock_run, _mock_platform):
        """Handles null model and transport gracefully."""
        data = {
            "blockdevices": [
                {
                    "name": "vda",
                    "size": 21474836480,
                    "model": None,
                    "tran": None,
                    "type": "disk",
                    "mountpoint": None,
                    "rm": False,
                    "ro": False,
                }
            ]
        }
        mock_run.side_effect = _make_run_side_effect(data)
        disks = _list_disks_linux()
        assert len(disks) == 1
        assert disks[0].model is None
        assert disks[0].protocol is None

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_whitespace_model_normalized(self, mock_run, _mock_platform):
        """Model strings with only whitespace become None."""
        data = {
            "blockdevices": [
                {
                    "name": "sda",
                    "size": 500107862016,
                    "model": "   ",
                    "tran": "sata",
                    "type": "disk",
                    "mountpoint": None,
                    "rm": False,
                    "ro": False,
                }
            ]
        }
        mock_run.side_effect = _make_run_side_effect(data)
        disks = _list_disks_linux()
        assert disks[0].model is None

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_removable_flag_as_int(self, mock_run, _mock_platform):
        """rm=1 (integer) should be treated as removable/external."""
        data = {
            "blockdevices": [
                {
                    "name": "sdb",
                    "size": 64000000000,
                    "model": "Flash Drive",
                    "tran": "usb",
                    "type": "disk",
                    "mountpoint": None,
                    "rm": 1,
                    "ro": False,
                }
            ]
        }
        mock_run.side_effect = _make_run_side_effect(data)
        disks = _list_disks_linux()
        assert disks[0].is_external is True

    @patch("disk_health_checker.utils.disks.get_platform_info", return_value=_make_linux_platform())
    @patch("disk_health_checker.utils.disks.subprocess.run")
    def test_removable_flag_as_string(self, mock_run, _mock_platform):
        """rm="1" (string) should be treated as removable/external."""
        data = {
            "blockdevices": [
                {
                    "name": "sdb",
                    "size": 64000000000,
                    "model": "Flash Drive",
                    "tran": "usb",
                    "type": "disk",
                    "mountpoint": None,
                    "rm": "1",
                    "ro": False,
                }
            ]
        }
        mock_run.side_effect = _make_run_side_effect(data)
        disks = _list_disks_linux()
        assert disks[0].is_external is True


class TestListDisksDispatch:
    """list_disks() dispatches to the right platform implementation."""

    @patch("disk_health_checker.utils.disks.get_platform_info")
    @patch("disk_health_checker.utils.disks._list_disks_linux")
    def test_dispatches_to_linux(self, mock_linux, mock_platform):
        from disk_health_checker.utils.disks import list_disks
        from disk_health_checker.utils.platform import PlatformInfo

        mock_platform.return_value = PlatformInfo(
            system="Linux", release="6.1.0", is_linux=True, is_macos=False
        )
        mock_linux.return_value = []
        list_disks()
        mock_linux.assert_called_once()

    @patch("disk_health_checker.utils.disks.get_platform_info")
    def test_unsupported_platform_returns_empty(self, mock_platform):
        from disk_health_checker.utils.disks import list_disks
        from disk_health_checker.utils.platform import PlatformInfo

        mock_platform.return_value = PlatformInfo(
            system="Windows", release="10", is_linux=False, is_macos=False
        )
        assert list_disks() == []
