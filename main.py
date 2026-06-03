from __future__ import annotations

# DPI awareness — must be set before any window/UI object.
try:
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from app.main import main

if __name__ == "__main__":
    main()
