"""Input validation utilities.

Validates untrusted inputs at system boundaries: device paths from CLI
arguments, file paths from manifest files, and algorithm names from
external JSON.
"""

from __future__ import annotations

import os
import re

# Device path allowlist — covers macOS and common Linux device naming.
# Only matches paths under /dev/ with known device name patterns.
_VALID_DEVICE_RE = re.compile(
    r"^/dev/"
    r"(?:r?disk\d+"                     # macOS: disk0, rdisk2
    r"|[sv]d[a-z]{1,3}\d*"             # Linux SCSI/SATA/virtio: sda, sda1, vdb
    r"|nvme\d+n\d+(?:p\d+)?"           # Linux NVMe: nvme0n1, nvme0n1p1
    r"|mmcblk\d+(?:p\d+)?"             # Linux eMMC/SD: mmcblk0, mmcblk0p1
    r"|xvd[a-z]{1,3}\d*"              # Xen virtual disks
    r"|loop\d+"                         # Loop devices
    r"|dm-\d+"                          # Device-mapper
    r"|md\d+"                           # Software RAID
    r")$"
)


def validate_device_path(device: str) -> str:
    """Validate that *device* looks like a real block device path.

    Raises ``ValueError`` for anything that doesn't match the allowlist.
    This prevents argument-injection when the path is passed to
    ``subprocess.run([..., device])``.
    """
    if not device or not _VALID_DEVICE_RE.match(device):
        raise ValueError(
            f"Invalid device path: {device!r}. "
            "Expected a path like /dev/disk0, /dev/sda, /dev/nvme0n1, etc."
        )
    return device


def safe_path(base: str, untrusted_rel: str) -> str:
    """Resolve *untrusted_rel* under *base*, rejecting path traversal.

    Both paths are resolved via ``os.path.realpath`` to eliminate
    symlinks and ``..`` components.  The result must start with *base*
    (plus a path separator) to prevent escapes.

    Raises ``ValueError`` if the resolved path escapes *base*.
    """
    real_base = os.path.realpath(base)
    real_joined = os.path.realpath(os.path.join(real_base, untrusted_rel))
    if real_joined != real_base and not real_joined.startswith(real_base + os.sep):
        raise ValueError(
            f"Path traversal blocked: {untrusted_rel!r} escapes {base}"
        )
    return real_joined


# Algorithms that are safe and performant for integrity verification.
ALLOWED_HASH_ALGORITHMS = frozenset({"sha256", "sha384", "sha512", "blake2b"})


def validate_hash_algorithm(algo: str) -> str:
    """Validate that *algo* is in the allowlist.

    Raises ``ValueError`` for unsupported or weak algorithms.
    """
    if algo not in ALLOWED_HASH_ALGORITHMS:
        raise ValueError(
            f"Unsupported hash algorithm: {algo!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_HASH_ALGORITHMS))}"
        )
    return algo
