from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
from typing import Dict, Any

from ..models.config import FsConfig, GlobalConfig
from ..models.results import CheckResult, Severity
from ..utils.platform import get_platform_info, which

logger = logging.getLogger(__name__)


def _get_fs_type(path: str) -> str:
    info = get_platform_info()
    if info.is_linux:
        try:
            with open("/proc/mounts", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == path:
                        return parts[2]
        except OSError:
            pass
    # Fallback: not always accurate but better than nothing
    try:
        st = os.statvfs(path)
        # On many systems, f_fsid or f_flag are not very helpful for type, so just return "unknown"
        return "unknown"
    except OSError:
        return "unknown"


def _run_fsck_if_requested(path: str, run_external_fsck: bool) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    if not run_external_fsck:
        return details

    info = get_platform_info()
    if not info.is_linux:
        details["fsck"] = "external fsck not supported on this platform by this tool"
        return details

    fsck = which("fsck")
    if not fsck:
        details["fsck"] = "fsck not found on PATH"
        return details

    # Try non-destructive check (-n: no changes). We currently do not know
    # the underlying device from the mount path, so this is a documented stub.
    try:
        # We already know fsck exists from the which() check above; calling it
        # without a mapped device would be misleading, so we explain the skip.
        details["fsck"] = "fsck invocation skipped (device mapping from mount point not implemented)"
    except Exception as exc:  # pragma: no cover - defensive
        details["fsck_error"] = str(exc)
    return details


def run_filesystem_check(config: FsConfig, global_config: GlobalConfig) -> CheckResult:
    mount = config.mount_point

    if not os.path.exists(mount):
        return CheckResult(
            check_name="Filesystem",
            status=Severity.CRITICAL,
            summary=f"Mount point does not exist: {mount}",
            details={},
            recommendations=[f"Ensure the filesystem at {mount} is mounted and accessible."],
        )

    details: Dict[str, Any] = {}

    fs_type = _get_fs_type(mount)
    details["filesystem_type"] = fs_type

    try:
        usage = shutil.disk_usage(mount)
        details["total_bytes"] = usage.total
        details["used_bytes"] = usage.used
        details["free_bytes"] = usage.free
    except OSError as exc:
        logger.warning("Failed to get disk usage for %s: %s", mount, exc)

    # Basic read/write sanity check if allowed
    recommendations = []
    sanity_ok = True
    if global_config.non_destructive:
        # still safe to do a very small create/delete in a temp dir
        try:
            with tempfile.NamedTemporaryFile(dir=mount, prefix=".dhc-fs-test-", delete=True) as tmp:
                tmp.write(b"disk-health-checker fs test\n")
                tmp.flush()
                os.fsync(tmp.fileno())
        except Exception as exc:
            sanity_ok = False
            details["sanity_check_error"] = str(exc)
            recommendations.append(
                f"Failed to create a small file under {mount}; check permissions and mount options (e.g. read-only)."
            )
    else:
        # In non-destructive-disabled mode, the caller has opted into more
        # intensive operations elsewhere; we keep this quick sanity check
        # disabled to avoid surprising writes here.
        details["sanity_check"] = "skipped because non-destructive safeguards are disabled for this run"

    # External fsck (non-destructive mode only, and optional)
    details.update(_run_fsck_if_requested(mount, config.run_external_fsck))

    # Basic permission info
    try:
        st = os.stat(mount)
        details["mode"] = oct(stat.S_IMODE(st.st_mode))
    except OSError:
        pass

    if not sanity_ok:
        status = Severity.CRITICAL
        summary = f"Filesystem at {mount} is accessible but basic write test failed."
    else:
        status = Severity.OK
        summary = f"Filesystem at {mount} appears healthy for basic operations."

    return CheckResult(
        check_name="Filesystem",
        status=status,
        summary=summary,
        details=details,
        recommendations=recommendations,
    )


