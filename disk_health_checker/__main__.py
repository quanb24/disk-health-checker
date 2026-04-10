"""Allow running as `python -m disk_health_checker`."""

import sys

from disk_health_checker.cli import main

sys.exit(main())
