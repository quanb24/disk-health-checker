from __future__ import annotations

import sys
import time
from typing import Optional


class SimpleProgress:
    """
    Minimal progress indicator for long-running checks.
    Designed to be disabled when JSON output is requested.
    """

    def __init__(self, total: Optional[int] = None, prefix: str = "") -> None:
        self.total = total
        self.prefix = prefix
        self.start_time = time.time()
        self.last_update = 0.0

    def update(self, current: int) -> None:
        now = time.time()
        # Limit updates to avoid excessive output
        if now - self.last_update < 0.5:
            return
        self.last_update = now

        if self.total:
            fraction = min(max(current / self.total, 0.0), 1.0)
            percent = int(fraction * 100)
            elapsed = now - self.start_time
            msg = f"\r{self.prefix}{percent:3d}% ({current}/{self.total}) elapsed {int(elapsed)}s"
        else:
            elapsed = now - self.start_time
            msg = f"\r{self.prefix}{current} units processed, elapsed {int(elapsed)}s"

        sys.stderr.write(msg)
        sys.stderr.flush()

    def done(self) -> None:
        sys.stderr.write("\n")
        sys.stderr.flush()


