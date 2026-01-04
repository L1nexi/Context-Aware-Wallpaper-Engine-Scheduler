import sys
import os

def get_app_root() -> str:
    """
    Returns the application root directory.
    Handles both script execution and PyInstaller frozen executable.
    """
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app 
        # path into variable _MEIPASS'.
        # However, for external config files, we want the directory of the executable
        return os.path.dirname(sys.executable)
    else:
        # Normal python script execution
        # Assuming this file is in utils/app_context.py, so root is one level up
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
