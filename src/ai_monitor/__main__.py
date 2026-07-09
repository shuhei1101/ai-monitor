from __future__ import annotations

import sys


def main() -> int:
    from ai_monitor.main import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
