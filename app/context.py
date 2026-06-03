import os
import sys
from pathlib import Path


def get_app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return str(Path(__file__).resolve().parents[1])


def get_data_dir() -> str:
    path = os.path.join(get_app_root(), "data")
    os.makedirs(path, exist_ok=True)
    return path
