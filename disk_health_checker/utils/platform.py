from __future__ import annotations

import os
import platform
import shutil
import stat
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlatformInfo:
    system: str
    release: str
    is_linux: bool
    is_macos: bool


def get_platform_info() -> PlatformInfo:
    system = platform.system()
    return PlatformInfo(
        system=system,
        release=platform.release(),
        is_linux=system == "Linux",
        is_macos=system == "Darwin",
    )


def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def is_block_device(path: str) -> bool:
    try:
        st = os.stat(path)
    except OSError:
        return False
    return stat.S_ISBLK(st.st_mode)



