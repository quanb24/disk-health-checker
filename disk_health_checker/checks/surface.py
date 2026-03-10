from __future__ import annotations

import logging
import os
import time
from typing import Dict, Any

from ..models.config import SurfaceScanConfig, GlobalConfig
from ..models.results import CheckResult, Severity
from ..utils.io import safe_open_readonly
from ..utils.progress import SimpleProgress

logger = logging.getLogger(__name__)


def run_surface_scan(config: SurfaceScanConfig, global_config: GlobalConfig) -> CheckResult:
    """
    Perform a simple read-only surface scan.

    In quick mode, we sample every Nth block. In full mode, we read sequentially.
    """
    device = config.device

    if not os.path.exists(device):
        return CheckResult(
            check_name="SurfaceScan",
            status=Severity.CRITICAL,
            summary=f"Device does not exist: {device}",
            details={},
            recommendations=[f"Ensure the device path {device} is correct and accessible."],
        )

    block_size = max(config.block_size, 4096)
    sample_rate = max(config.sample_rate, 1)

    total_bytes = None
    try:
        total_bytes = os.path.getsize(device)
    except OSError:
        # For raw block devices, getsize may fail; that's acceptable.
        pass

    total_blocks = None
    total_samples = None
    if total_bytes is not None:
        total_blocks = max(total_bytes // block_size, 1)
        if config.quick:
            # In quick mode we only read a subset of blocks; progress should
            # reflect the number of samples rather than total blocks.
            total_samples = max(total_blocks // sample_rate, 1)
        else:
            total_samples = total_blocks

    if global_config.json_output:
        progress = None
    else:
        progress = SimpleProgress(total=total_samples, prefix="Surface scan: ")

    blocks_read = 0
    errors = 0
    slow_blocks = 0
    latencies = []
    max_latency = 0.0

    start_time = time.time()
    deadline = start_time + config.max_duration_seconds if config.max_duration_seconds else None

    try:
        with safe_open_readonly(device) as f:
            while True:
                if deadline and time.time() > deadline:
                    logger.info("Surface scan reached max duration, stopping early.")
                    break

                try:
                    offset = None
                    if config.quick and total_blocks is not None:
                        offset = blocks_read * block_size * sample_rate
                        if offset >= total_bytes:
                            break
                        f.seek(offset)

                    t0 = time.time()
                    data = f.read(block_size)
                    t1 = time.time()
                    if not data:
                        break
                    latency = t1 - t0
                    latencies.append(latency)
                    if latency > 0.1:  # 100ms threshold for "slow"
                        slow_blocks += 1
                    if latency > max_latency:
                        max_latency = latency
                except OSError as exc:
                    logger.warning("Read error during surface scan at block %d: %s", blocks_read, exc)
                    errors += 1

                blocks_read += 1
                if progress and total_samples:
                    progress.update(blocks_read)

    except OSError as exc:
        logger.warning("Failed to open device %s for surface scan: %s", device, exc)
        return CheckResult(
            check_name="SurfaceScan",
            status=Severity.UNKNOWN,
            summary=f"Surface scan unavailable: {exc}",
            details={},
            recommendations=[
                "Run as a privileged user and ensure the device supports raw reads.",
            ],
        )
    finally:
        if progress:
            progress.done()

    elapsed = time.time() - start_time

    details: Dict[str, Any] = {
        "device": device,
        "blocks_read": blocks_read,
        "errors": errors,
        "slow_blocks": slow_blocks,
        "elapsed_seconds": elapsed,
        "block_size": block_size,
        "quick_mode": config.quick,
        "max_latency_seconds": max_latency,
    }

    status = Severity.OK
    recommendations = []
    summary_parts = []

    if errors > 0:
        status = Severity.CRITICAL
        summary_parts.append(f"{errors} read errors encountered during surface scan")
        recommendations.append("Back up data and consider replacing the drive.")

    if slow_blocks > 0 and status != Severity.CRITICAL:
        status = Severity.WARNING
        summary_parts.append(f"{slow_blocks} slow blocks observed (>100ms read latency)")
        recommendations.append("Monitor performance; slow regions may indicate early degradation.")

    if not summary_parts:
        summary_parts.append("No errors detected during sampled surface scan.")

    return CheckResult(
        check_name="SurfaceScan",
        status=status,
        summary="; ".join(summary_parts),
        details=details,
        recommendations=recommendations,
    )


