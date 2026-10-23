"""PyInstaller entry point. Kept at project root so `harnessboard` is importable."""
from harnessboard.app import main

if __name__ == "__main__":
    raise SystemExit(main())
