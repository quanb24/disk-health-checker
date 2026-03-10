from __future__ import annotations

import os
from typing import BinaryIO


def safe_open_readonly(path: str) -> BinaryIO:
    """
    Open a path for read-only binary access, raising IOError on failure.
    Intended for use with device paths or regular files.
    """
    return open(path, "rb", buffering=0)


def iter_read_chunks(f: BinaryIO, chunk_size: int):
    while True:
        data = f.read(chunk_size)
        if not data:
            break
        yield data


