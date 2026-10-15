#!/usr/bin/env python3
"""Backward-compatible entrypoint; prefers run_local.py for full local bootstrap."""

from run_local import main


if __name__ == "__main__":
    raise SystemExit(main())
