from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GlobalConfig:
    non_destructive: bool = True
    json_output: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = None


@dataclass
class SmartConfig:
    device: str
    skip_extended_self_tests: bool = True


@dataclass
class FsConfig:
    mount_point: str
    run_external_fsck: bool = False


@dataclass
class SurfaceScanConfig:
    device: str
    quick: bool = True
    block_size: int = 1024 * 1024  # 1 MiB
    sample_rate: int = 1024  # read every Nth block in quick mode
    max_duration_seconds: Optional[int] = None


@dataclass
class StressConfig:
    mount_point: str
    duration_seconds: int = 300
    threads: int = 4
    max_space_fraction: float = 0.1


@dataclass
class IntegrityConfig:
    mount_point: str
    manifest_path: Optional[str] = None
    algorithm: str = "sha256"
    max_file_size_bytes: int = 1024 * 1024 * 1024  # 1 GiB per file
    max_total_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB total


