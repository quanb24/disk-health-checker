from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import List

from .core.runner import run_full_suite
from .core.macos_full import run_macos_full_workflow
from .core.doctor import run_doctor
from .models.config import (
    GlobalConfig,
    SmartConfig,
    FsConfig,
    SurfaceScanConfig,
    StressConfig,
    IntegrityConfig,
)
from .models.results import Severity, SuiteResult
from .checks.smart import run_smart_check
from .checks.filesystem import run_filesystem_check
from .checks.surface import run_surface_scan
from .checks.stress import run_stress_test
from .checks.integrity import run_integrity_check
from .utils.logging import setup_logging
from .utils.disks import list_disks, select_disk_interactively
from .utils.platform import get_platform_info


def _build_parser() -> argparse.ArgumentParser:
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="disk-health-checker",
        description="Check the health of a recently formatted disk (SMART, filesystem, surface, stress, integrity).",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional path to a log file.",
    )
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="Allow more intensive operations. Use with care.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Shared --json flag for subparsers so it works both before and after
    # the subcommand name (e.g. `--json smart` AND `smart --json`).
    _json_parent = argparse.ArgumentParser(add_help=False)
    _json_parent.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        dest="json",
        help="Output results as JSON.",
    )

    # detect
    detect = subparsers.add_parser(
        "detect",
        help="List connected disks (macOS: via diskutil).",
    )
    detect.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional details where available.",
    )

    # full suite (macOS-focused workflow by default)
    full = subparsers.add_parser(
        "full", parents=[_json_parent],
        help="Run a safe, non-destructive validation workflow.",
    )
    full.add_argument(
        "--device",
        help="Block device path (e.g. /dev/disk2). If omitted on macOS, you will be prompted to select a disk.",
    )

    # SMART
    smart = subparsers.add_parser(
        "smart", parents=[_json_parent],
        help="Run SMART diagnostics and health assessment.",
    )
    smart.add_argument(
        "--device",
        help="Block device path (e.g. /dev/disk2). If omitted on macOS, you will be prompted to select a disk.",
    )

    # filesystem
    fs = subparsers.add_parser("fs", parents=[_json_parent], help="Run filesystem verification only.")
    fs.add_argument("--mount", required=True, help="Filesystem mount point.")
    fs.add_argument(
        "--fsck",
        action="store_true",
        help="Attempt non-destructive external fsck where supported.",
    )

    # surface
    surface = subparsers.add_parser("surface", parents=[_json_parent], help="Run disk surface scan only.")
    surface.add_argument("--device", required=True, help="Block device path (e.g. /dev/sdX).")
    surface.add_argument(
        "--full",
        action="store_true",
        help="Run a full sequential scan instead of the default quick sampled scan (may be very slow).",
    )

    # stress
    stress = subparsers.add_parser("stress", parents=[_json_parent], help="Run read/write stress test only.")
    stress.add_argument("--mount", required=True, help="Filesystem mount point.")
    stress.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Duration in seconds (default: 300).",
    )
    stress.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Number of worker threads (default: 4).",
    )
    stress.add_argument(
        "--space-fraction",
        type=float,
        default=0.1,
        help="Maximum fraction of free space to use (default: 0.1).",
    )

    # integrity
    integrity = subparsers.add_parser("integrity", parents=[_json_parent], help="Run data integrity verification only.")
    integrity.add_argument("--mount", required=True, help="Filesystem mount point.")
    integrity.add_argument(
        "--manifest",
        help="Optional path to a checksum manifest JSON file.",
    )
    integrity.add_argument(
        "--algo",
        default="sha256",
        help="Hash algorithm for manifest checks (default: sha256).",
    )

    # doctor / explain
    doctor = subparsers.add_parser(
        "doctor", parents=[_json_parent],
        help="Explain SMART results in beginner-friendly language and suggest next steps.",
    )
    doctor.add_argument(
        "--device",
        help="Block device path (e.g. /dev/disk2). If omitted on macOS, you will be prompted to select a disk.",
    )

    return parser


def _format_capacity(nbytes: int | None) -> str:
    if nbytes is None or nbytes <= 0:
        return "unknown"
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"  # pragma: no cover


def _format_hours(hours: int | None) -> str:
    if hours is None:
        return "unknown"
    if hours < 24:
        return f"{hours} hours"
    days = hours // 24
    if days < 365:
        return f"~{days:,} days ({hours:,} hours)"
    years = days / 365.25
    return f"~{years:.1f} years ({hours:,} hours)"


def _print_smart_banner(check) -> None:
    """Print the new verdict-first banner for a SMART check result."""
    d = check.details

    # ---- Drive identity ----
    model = d.get("model_name") or "Unknown model"
    serial = d.get("serial_number") or ""
    firmware = d.get("firmware_version") or ""
    capacity = _format_capacity(d.get("capacity_bytes"))

    # Determine drive interface from findings/device_kind or fall back.
    device_kind = d.get("device_kind", "")
    kind_label = device_kind.upper() if device_kind else ""

    print(f"Disk:      {model}" + (f"  ({kind_label})" if kind_label else ""))
    identity_parts = []
    if firmware:
        identity_parts.append(f"Firmware: {firmware}")
    if serial:
        # Truncate serial for privacy in shared terminals.
        display_serial = serial[:10] + "..." if len(serial) > 10 else serial
        identity_parts.append(f"Serial: {display_serial}")
    identity_parts.append(f"Capacity: {capacity}")
    if identity_parts:
        print(f"           {', '.join(identity_parts)}")

    poh = d.get("power_on_hours")
    drive_type = "SSD" if d.get("is_ssd") else "HDD" if d.get("rotation_rate_rpm") else ""
    age_line_parts = []
    if poh is not None:
        age_line_parts.append(f"Age: {_format_hours(poh)}")
    if drive_type:
        age_line_parts.append(f"Type: {drive_type}")
    if age_line_parts:
        print(f"           {'  |  '.join(age_line_parts)}")

    print()

    # ---- Verdict ----
    verdict = d.get("verdict", check.status.value)
    confidence = d.get("confidence", "")
    score = d.get("health_score")
    score_str = f"score {score}/100, " if score is not None else ""
    conf_str = f"confidence {confidence}" if confidence else ""
    print(f"Verdict:   {verdict}  ({score_str}{conf_str})")

    # ---- Findings ----
    findings = d.get("findings", [])
    if findings:
        print()
        print("Why:")
        for f in findings:
            sev = f.get("severity", "")
            marker = {"FAIL": "!!", "WARN": "!", "INFO": " "}.get(sev, " ")
            print(f"  {marker} {f.get('message', '')}")

    # ---- Evidence gaps ----
    missing = d.get("evidence_missing", [])
    if missing:
        print()
        print(f"Signals missing: {', '.join(missing)}")
    elif findings is not None:
        # Only show "none" when we actually checked.
        print()
        print("Signals missing: none")

    # ---- Recommendations ----
    if check.recommendations:
        print()
        print("Next steps:")
        for i, rec in enumerate(check.recommendations, 1):
            print(f"  {i}. {rec}")


def _print_usb_blocked_banner(check) -> None:
    """Print a clear explanation when a USB enclosure blocks SMART."""
    print("Verdict:   UNKNOWN")
    print()
    print("Reason:    USB enclosure is blocking SMART passthrough")
    print()
    print("  The USB-to-SATA bridge chip inside this external enclosure")
    print("  is preventing SMART health data from reaching the host.")
    print("  This does NOT mean the drive is failing — it means health")
    print("  cannot be assessed through this connection.")
    print()
    types_tried = check.details.get("device_types_tried", [])
    if types_tried:
        print(f"  Modes tried: {', '.join(types_tried)}")
        print()
    if check.recommendations:
        print("What you can do:")
        for i, rec in enumerate(check.recommendations, 1):
            print(f"  {i}. {rec}")


def _print_error_banner(check) -> None:
    """Print a clean banner for SMART errors (not installed, timeout, etc.)."""
    reason = check.details.get("failure_reason", "unknown")
    reason_labels = {
        "smartctl_not_installed": "smartctl is not installed",
        "smart_not_supported": "SMART not supported on this device",
        "timeout": "smartctl timed out waiting for the drive",
        "unknown": "SMART check failed",
    }
    label = reason_labels.get(reason, "SMART check failed")

    print("Verdict:   UNKNOWN")
    print()
    print(f"Reason:    {label}")
    print()
    if check.summary:
        print(f"  {check.summary}")
        print()
    if check.recommendations:
        print("Next steps:")
        for i, rec in enumerate(check.recommendations, 1):
            print(f"  {i}. {rec}")


def _print_human_suite(result: SuiteResult) -> None:
    """Print human-readable output.

    For SMART-based checks that carry the new verdict/findings structure,
    use the banner format.  For legacy checks (filesystem, surface, etc.)
    and multi-check suites, fall back to the structured report.
    """
    # Single-check SMART result with verdict data -> banner format.
    if len(result.check_results) == 1:
        single = result.check_results[0]
        if "verdict" in single.details:
            _print_smart_banner(single)
            return
        if single.details.get("failure_reason") == "usb_bridge_blocked":
            _print_usb_blocked_banner(single)
            return
        if "failure_reason" in single.details:
            _print_error_banner(single)
            return

    # Multi-check suite (e.g. `full` command) or legacy checks.
    print(f"Disk Health Check — {result.target}")
    print(f"Overall: {result.overall_status.value}")
    print()

    for check in result.check_results:
        if "verdict" in check.details:
            # SMART check within a suite — use banner.
            _print_smart_banner(check)
            print()
            print("-" * 60)
            print()
        elif check.details.get("failure_reason") == "usb_bridge_blocked":
            _print_usb_blocked_banner(check)
            print()
        elif "failure_reason" in check.details:
            _print_error_banner(check)
            print()
        else:
            # Legacy check — simple format.
            print(f"=== {check.check_name} ===")
            print(f"Status: {check.status.value}")
            print(f"Summary: {check.summary}")
            if check.recommendations:
                print("Recommendations:")
                for rec in check.recommendations:
                    print(f"  - {rec}")
            print()


def _exit_code_from_severity(sev: Severity) -> int:
    if sev == Severity.OK:
        return 0
    if sev == Severity.WARNING:
        return 1
    if sev == Severity.CRITICAL:
        return 2
    return 3


def _resolve_device(
    args: argparse.Namespace, info, *, json_mode: bool
) -> tuple[str, str | None] | None:
    """Resolve the target device from --device or interactive selection.

    Returns ``(device_path, transport)`` on success, or ``None`` if
    resolution failed (caller should print an appropriate message and
    return exit code 1).

    *transport* is the bus protocol (e.g. ``"USB"``, ``"NVMe"``) when
    known from disk enumeration, or ``None`` when the device was given
    via ``--device`` without interactive selection.

    When *json_mode* is True, interactive selection is skipped to prevent
    deadlocking automation pipelines that consume JSON stdout.
    """
    device = getattr(args, "device", None)
    if device:
        # When --device is given directly we don't know the transport.
        # Try a quick lookup on macOS so USB fallback still works.
        transport = None
        if info.is_macos:
            for d in list_disks():
                if d.device_node == device:
                    transport = d.protocol
                    break
        return device, transport

    if json_mode:
        print(
            "Error: --device is required when --json is set. "
            "Interactive disk selection is disabled in JSON mode.",
            file=sys.stderr,
        )
        return None

    if info.is_macos:
        disks = list_disks()
        selected = select_disk_interactively(disks)
        if selected:
            return selected.device_node, selected.protocol
        print("No disk selected; aborting.")
        return None

    print("A --device must be provided when automatic disk detection is not available.")
    return None


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    global_config = GlobalConfig(
        non_destructive=not args.allow_destructive,
        json_output=args.json,
        log_level=args.log_level,
        log_file=args.log_file,
    )
    setup_logging(level=global_config.log_level, log_file=global_config.log_file)

    logging.getLogger(__name__).debug("Starting disk-health-checker with args: %s", args)

    info = get_platform_info()

    # detect command
    if args.command == "detect":
        disks = list_disks()
        if not disks:
            print("No disks detected automatically. On macOS, 'diskutil list -plist' must be available.")
            return 1
        print("Detected disks:")
        for d in disks:
            location = "internal" if d.is_internal else "external" if d.is_external else "unknown location"
            model = d.model or "Unknown model"
            proto = d.protocol or "Unknown bus"
            mounts = ", ".join(d.mount_points) if d.mount_points else "no mounted volumes"
            if args.verbose:
                print(
                    f"- {d.device_node}: {d.size_human}, {location}, {model}, {proto}, mounts: {mounts}"
                )
            else:
                print(f"- {d.device_node}: {d.size_human}, {location}, mounts: {mounts}")
        return 0

    # Commands that require a device path: full, smart, doctor.
    device = None
    transport = None
    if args.command in ("full", "smart", "doctor"):
        resolved = _resolve_device(args, info, json_mode=args.json)
        if not resolved:
            return 1
        device, transport = resolved

    # full command
    if args.command == "full":
        if info.is_macos:
            suite = run_macos_full_workflow(device=device, global_config=global_config)
        else:
            # The generic suite hardcoded mount_point="/" which caused
            # stress/integrity writes to target the host root filesystem.
            # Disable until a proper Linux workflow is designed.
            print(
                "Error: 'full' is currently only supported on macOS.\n"
                "On Linux, use individual commands instead:\n"
                "  disk-health-checker smart --device /dev/sdX\n"
                "  disk-health-checker doctor --device /dev/sdX",
                file=sys.stderr,
            )
            return 1

        if args.json:
            print(json.dumps(suite.to_dict(), indent=2))
        else:
            _print_human_suite(suite)
        return _exit_code_from_severity(suite.overall_status)

    # Individual checks
    start = datetime.now(timezone.utc)
    check_result = None
    target_desc = ""

    if args.command == "smart":
        cfg = SmartConfig(device=device)
        check_result = run_smart_check(cfg, transport=transport)
        target_desc = f"device={device}"
    elif args.command == "fs":
        cfg = FsConfig(mount_point=args.mount, run_external_fsck=args.fsck)
        check_result = run_filesystem_check(cfg, global_config)
        target_desc = f"mount={args.mount}"
    elif args.command == "surface":
        cfg = SurfaceScanConfig(device=args.device, quick=not args.full)
        check_result = run_surface_scan(cfg, global_config)
        target_desc = f"device={args.device}"
    elif args.command == "stress":
        if not args.allow_destructive:
            print(
                "Error: 'stress' performs write operations and requires --allow-destructive.\n"
                "  disk-health-checker --allow-destructive stress --mount /Volumes/MyDisk",
                file=sys.stderr,
            )
            return 1
        cfg = StressConfig(
            mount_point=args.mount,
            duration_seconds=args.duration,
            threads=args.threads,
            max_space_fraction=args.space_fraction,
        )
        check_result = run_stress_test(cfg, global_config)
        target_desc = f"mount={args.mount}"
    elif args.command == "integrity":
        if not args.allow_destructive:
            print(
                "Error: 'integrity' performs write operations and requires --allow-destructive.\n"
                "  disk-health-checker --allow-destructive integrity --mount /Volumes/MyDisk",
                file=sys.stderr,
            )
            return 1
        cfg = IntegrityConfig(
            mount_point=args.mount,
            manifest_path=args.manifest,
            algorithm=args.algo,
        )
        check_result = run_integrity_check(cfg, global_config)
        target_desc = f"mount={args.mount}"
    elif args.command == "doctor":
        check_result = run_doctor(device, transport=transport)
        target_desc = f"device={device}"
    else:  # pragma: no cover - defensive
        parser.error(f"Unknown command: {args.command}")

    assert check_result is not None
    suite = SuiteResult(
        target=target_desc,
        overall_status=check_result.status,
        check_results=[check_result],
        started_at=start,
        finished_at=datetime.now(timezone.utc),
    )

    if args.json:
        print(json.dumps(suite.to_dict(), indent=2))
    else:
        _print_human_suite(suite)

    return _exit_code_from_severity(check_result.status)


if __name__ == "__main__":
    sys.exit(main())

