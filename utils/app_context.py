import os
import sys


def get_app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_dir() -> str:
    path = os.path.join(get_app_root(), "data")
    os.makedirs(path, exist_ok=True)
    return path
