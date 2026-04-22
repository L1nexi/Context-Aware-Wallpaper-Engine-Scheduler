import sys
import os

def get_app_root() -> str:
    """
    Returns the application root directory.
    Handles both script execution and PyInstaller frozen executable.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_data_dir() -> str:
    """Returns the data directory (app_root/data), creating it if needed."""
    path = os.path.join(get_app_root(), "data")
    os.makedirs(path, exist_ok=True)
    return path
