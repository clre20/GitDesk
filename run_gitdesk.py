"""Entry point used by PyInstaller (and for running from source: python run_gitdesk.py)."""
import sys

from gitdesk.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
