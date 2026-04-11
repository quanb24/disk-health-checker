from __future__ import annotations

import json
import logging
import plistlib
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .platform import get_platform_info

logger = logging.getLogger(__name__)

# Seconds before giving up on disk-enumeration subprocesses.
# A stalled USB bridge or slow NFS mount can cause diskutil/lsblk to hang.
_ENUM_TIMEOUT_S = 15


@dataclass
class DiskInfo:
    identifier: str
    device_node: str
    size_bytes: Optional[int]
    model: Optional[str]
    protocol: Optional[str]
    is_internal: Optional[bool]
    is_external: Optional[bool]
    is_virtual: Optional[bool]
    mount_points: List[str]

    @property
    def size_human(self) -> str:
        if self.size_bytes is None or self.size_bytes <= 0:
            return "unknown size"
        size = float(self.size_bytes)
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        return f"{size:.1f} {units[idx]}"


def _list_disks_macos() -> List[DiskInfo]:
    info = get_platform_info()
    if not info.is_macos:
        return []

    try:
        proc = subprocess.run(
            ["diskutil", "list", "-plist"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=_ENUM_TIMEOUT_S,
        )
    except FileNotFoundError:
        return []
    except subprocess.CalledProcessError:
        return []
    except subprocess.TimeoutExpired:
        logger.warning("diskutil list timed out after %ds", _ENUM_TIMEOUT_S)
        return []

    data = plistlib.loads(proc.stdout)
    disks = []
    for entry in data.get("AllDisksAndPartitions", []):
        ident = entry.get("DeviceIdentifier")
        if not ident:
            continue
        device_node = f"/dev/{ident}"
        size_bytes = entry.get("Size")

        # Collect mount points for this disk and its partitions
        mounts: List[str] = []
        if entry.get("MountPoint"):
            mounts.append(entry["MountPoint"])
        for part in entry.get("Partitions", []):
            mp = part.get("MountPoint")
            if mp:
                mounts.append(mp)

        # Enrich with diskutil info for model/protocol where possible
        model = None
        protocol = None
        is_internal = None
        is_external = None
        is_virtual = None
        try:
            info_proc = subprocess.run(
                ["diskutil", "info", "-plist", device_node],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=_ENUM_TIMEOUT_S,
            )
            inf = plistlib.loads(info_proc.stdout)
            model = (
                inf.get("DeviceModel")
                or inf.get("MediaName")
                or inf.get("IORegistryEntryName")
            )
            protocol = inf.get("BusProtocol")
            internal = inf.get("Internal")
            virtual = inf.get("VirtualOrPhysical") == "Virtual"
            is_internal = bool(internal) if internal is not None else None
            is_virtual = virtual
            if is_internal is not None:
                is_external = not is_internal
        except Exception:
            # Best-effort enrichment only
            pass

        disks.append(
            DiskInfo(
                identifier=ident,
                device_node=device_node,
                size_bytes=size_bytes,
                model=model,
                protocol=protocol,
                is_internal=is_internal,
                is_external=is_external,
                is_virtual=is_virtual,
                mount_points=mounts,
            )
        )
    return disks


def _list_disks_linux() -> List[DiskInfo]:
    """Enumerate physical block devices on Linux using ``lsblk --json``.

    Filters to whole-disk devices only (TYPE == "disk"), skipping
    partitions, loop devices, and device-mapper entries.
    """
    try:
        proc = subprocess.run(
            [
                "lsblk",
                "--json",
                "--bytes",
                "--output", "NAME,SIZE,MODEL,TRAN,TYPE,MOUNTPOINT,RM,RO",
                "--nodeps",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=_ENUM_TIMEOUT_S,
        )
    except FileNotFoundError:
        logger.warning("lsblk not found — cannot enumerate disks on this Linux system")
        return []
    except subprocess.CalledProcessError as exc:
        logger.warning("lsblk failed (exit %d): %s", exc.returncode, exc.stderr)
        return []
    except subprocess.TimeoutExpired:
        logger.warning("lsblk timed out after %ds", _ENUM_TIMEOUT_S)
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.warning("lsblk returned invalid JSON")
        return []

    blockdevices = data.get("blockdevices", [])
    disks: List[DiskInfo] = []

    for dev in blockdevices:
        dev_type = (dev.get("type") or "").lower()
        if dev_type != "disk":
            continue

        name = dev.get("name", "")
        if not name:
            continue

        device_node = f"/dev/{name}"
        size_bytes = dev.get("size")
        if isinstance(size_bytes, str):
            try:
                size_bytes = int(size_bytes)
            except ValueError:
                size_bytes = None

        model = dev.get("model")
        if isinstance(model, str):
            model = model.strip() or None

        tran = dev.get("tran")  # e.g. "sata", "nvme", "usb", "ata"
        protocol = tran.upper() if tran else None

        # removable flag: "1" or 1 means removable/external
        rm = dev.get("rm")
        is_removable = rm in (True, 1, "1")
        is_internal = not is_removable
        is_external = is_removable

        # Mount point — lsblk with --nodeps gives the whole-disk mount
        # (rare), but partitions are where mounts usually live. We do a
        # second pass below if needed.
        mount = dev.get("mountpoint")
        mount_points = [mount] if mount else []

        disks.append(
            DiskInfo(
                identifier=name,
                device_node=device_node,
                size_bytes=size_bytes,
                model=model,
                protocol=protocol,
                is_internal=is_internal,
                is_external=is_external,
                is_virtual=False,
                mount_points=mount_points,
            )
        )

    # Enrich mount points from partitions (a second, cheap lsblk call).
    if disks:
        _enrich_linux_mounts(disks)

    return disks


def _enrich_linux_mounts(disks: List[DiskInfo]) -> None:
    """Fill in mount points from child partitions of each disk."""
    try:
        proc = subprocess.run(
            [
                "lsblk",
                "--json",
                "--output", "NAME,MOUNTPOINT,PKNAME",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=_ENUM_TIMEOUT_S,
        )
    except Exception:
        return

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return

    # Build a map: parent disk name -> list of mount points
    disk_names = {d.identifier for d in disks}
    parent_mounts: dict[str, list[str]] = {name: [] for name in disk_names}

    for entry in data.get("blockdevices", []):
        _collect_mounts(entry, disk_names, parent_mounts)

    for d in disks:
        if d.identifier in parent_mounts:
            extra = [m for m in parent_mounts[d.identifier] if m not in d.mount_points]
            d.mount_points.extend(extra)


def _collect_mounts(
    entry: dict,
    disk_names: set[str],
    parent_mounts: dict[str, list[str]],
) -> None:
    """Recursively collect mount points, mapping them to their parent disk."""
    name = entry.get("name", "")
    pkname = entry.get("pkname")
    mount = entry.get("mountpoint")

    # Direct child of a tracked disk
    if pkname and pkname in disk_names and mount:
        parent_mounts[pkname].append(mount)
    # The disk itself
    elif name in disk_names and mount:
        parent_mounts[name].append(mount)

    # Recurse into children (lsblk tree output)
    for child in entry.get("children", []):
        # If child doesn't have pkname set, inherit from parent
        if not child.get("pkname") and name in disk_names:
            child["pkname"] = name
        _collect_mounts(child, disk_names, parent_mounts)


def list_disks() -> List[DiskInfo]:
    """List physical disks on the current platform.

    - **macOS**: uses ``diskutil list -plist``
    - **Linux**: uses ``lsblk --json``
    - **Other**: returns an empty list
    """
    info = get_platform_info()
    if info.is_macos:
        return _list_disks_macos()
    if info.is_linux:
        return _list_disks_linux()
    return []


def select_disk_interactively(disks: List[DiskInfo]) -> Optional[DiskInfo]:
    """
    Prompt the user to select a disk from the provided list.
    Returns the chosen DiskInfo, or None if selection is aborted.
    """
    if not disks:
        print("No disks detected.")
        return None

    print("Available disks:")
    for idx, d in enumerate(disks, start=1):
        location = "internal" if d.is_internal else "external" if d.is_external else "unknown location"
        model = d.model or "Unknown model"
        proto = d.protocol or "Unknown bus"
        print(
            f"  {idx}) {d.device_node} "
            f"({d.size_human}, {location}, {model}, {proto})"
        )

    while True:
        try:
            choice = input("Select a disk by number (or press Enter to cancel): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not choice:
            return None
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue
        idx = int(choice)
        if idx < 1 or idx > len(disks):
            print(f"Please enter a number between 1 and {len(disks)}.")
            continue
        return disks[idx - 1]


