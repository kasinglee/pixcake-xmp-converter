#!/usr/bin/env python3
"""Read app version from README.md badge: Version-vX.Y.Z"""

import re
import sys
from pathlib import Path


def read_version(readme_path=None):
    path = Path(readme_path or Path(__file__).with_name("README.md"))
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Version-v(\d+\.\d+\.\d+)", text)
    if not match:
        raise ValueError(f"Version badge not found in {path}")
    return match.group(1)


if __name__ == "__main__":
    try:
        print(read_version())
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
