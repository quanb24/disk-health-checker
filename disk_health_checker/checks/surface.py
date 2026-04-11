"""Read-only surface scan.

Reads blocks from a device (sampled in quick mode, sequential in full mode)
and reports read errors and slow blocks as structured findings.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List

from ..models.config import SurfaceScanConfig, GlobalConfig
from ..models.results import CheckResult
from ..models.smart_types import Confidence, Finding, FindingSeverity
from ..utils.io import safe_open_readonly
from ..utils.progress import SimpleProgress
from .evaluate import findings_to_verdict, verdict_to_check_result

logger = logging.getLogger(__name__)


def run_surface_scan(config: SurfaceScanConfig, global_config: GlobalConfig) -> CheckResult:
    device = config.device
    findings: List[Finding] = []
    evidence_missing: List[str] = []
    extra_details: Dict[str, Any] = {"device": device, "quick_mode": config.quick}

    # ── Device existence ──
    if not os.path.exists(device):
        findings.append(Finding(
            code="surface.device_not_found",
            severity=FindingSeverity.FAIL,
            message=f"Device does not exist: {device}",
            evidence={"device": device},
        ))
        vr = findings_to_verdict(
            findings, confidence=Confidence.HIGH, check_category="surface scan",
        )
        return verdict_to_check_result(
            "SurfaceScan", vr,
            extra_details=extra_details,
            target_description=device,
        )

    block_size = max(config.block_size, 4096)
    sample_rate = max(config.sample_rate, 1)

    total_bytes = None
    try:
        total_bytes = os.path.getsize(device)
    except OSError:
        pass

    total_blocks = None
    total_samples = None
    if total_bytes is not None:
        total_blocks = max(total_bytes // block_size, 1)
        total_samples = (
            max(total_blocks // sample_rate, 1) if config.quick else total_blocks
        )

    progress = None
    if not global_config.json_output:
        progress = SimpleProgress(total=total_samples, prefix="Surface scan: ")

    blocks_read = 0
    errors = 0
    slow_blocks = 0
    max_latency = 0.0

    start_time = time.time()
    deadline = (
        start_time + config.max_duration_seconds
        if config.max_duration_seconds
        else None
    )

    try:
        with safe_open_readonly(device) as f:
            while True:
                if deadline and time.time() > deadline:
                    logger.info("Surface scan reached max duration, stopping early.")
                    break

                try:
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
                    if latency > 0.1:
                        slow_blocks += 1
                    if latency > max_latency:
                        max_latency = latency
                except OSError as exc:
                    logger.warning(
                        "Read error during surface scan at block %d: %s",
                        blocks_read, exc,
                    )
                    errors += 1

                blocks_read += 1
                if progress and total_samples:
                    progress.update(blocks_read)

    except OSError as exc:
        logger.warning("Failed to open device %s for surface scan: %s", device, exc)
        findings.append(Finding(
            code="surface.access_denied",
            severity=FindingSeverity.FAIL,
            message=f"Cannot open device for reading: {exc}",
            evidence={"device": device, "error": str(exc)},
        ))
        vr = findings_to_verdict(
            findings, confidence=Confidence.LOW, check_category="surface scan",
        )
        return verdict_to_check_result(
            "SurfaceScan", vr,
            extra_details=extra_details,
            target_description=device,
        )
    finally:
        if progress:
            progress.done()

    elapsed = time.time() - start_time

    extra_details.update({
        "blocks_read": blocks_read,
        "errors": errors,
        "slow_blocks": slow_blocks,
        "elapsed_seconds": elapsed,
        "block_size": block_size,
        "max_latency_seconds": max_latency,
    })

    # ── Build findings from scan results ──
    if errors > 0:
        findings.append(Finding(
            code="surface.read_errors",
            severity=FindingSeverity.FAIL,
            message=f"{errors} read error(s) encountered during surface scan.",
            evidence={"error_count": errors, "blocks_read": blocks_read},
        ))

    if slow_blocks > 0:
        findings.append(Finding(
            code="surface.slow_blocks",
            severity=FindingSeverity.WARN,
            message=f"{slow_blocks} slow block(s) observed (>100ms read latency).",
            evidence={
                "slow_block_count": slow_blocks,
                "max_latency_seconds": max_latency,
            },
        ))

    confidence = Confidence.HIGH if blocks_read > 0 else Confidence.LOW

    vr = findings_to_verdict(
        findings,
        evidence_missing=evidence_missing,
        confidence=confidence,
        check_category="surface scan",
    )
    return verdict_to_check_result(
        "SurfaceScan", vr,
        extra_details=extra_details,
        target_description=device,
    )
