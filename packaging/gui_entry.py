"""PyInstaller entry point: the whole GUI in one file."""

from gtatools.gui import _fix_dpi, main

_fix_dpi()

if __name__ == "__main__":
    main()
