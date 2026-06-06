"""Entry-point for ``python -m worktrail``."""

from __future__ import annotations

import sys

from worktrail.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
