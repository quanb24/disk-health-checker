from __future__ import annotations

import plistlib
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .platform import get_platform_info


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
        )
    except FileNotFoundError:
        # diskutil should exist on macOS, but handle defensively
        return []
    except subprocess.CalledProcessError:
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


def list_disks() -> List[DiskInfo]:
    """
    List disks on the current platform.

    On macOS, uses `diskutil list -plist` for robust disk enumeration.
    On other platforms, currently returns an empty list (future extension point).
    """
    info = get_platform_info()
    if info.is_macos:
        return _list_disks_macos()
    # Non-macOS: could add /dev scanning here later.
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


