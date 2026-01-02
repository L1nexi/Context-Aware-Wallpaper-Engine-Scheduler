import win32gui
import win32process
import psutil
from typing import Dict

class WindowSensor:
    def get_active_window_info(self) -> Dict[str, str]:
        """
        Returns a dictionary containing the active window's title and process name.
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {"title": "", "process": ""}

            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                process_name = "Unknown"

            return {
                "title": title,
                "process": process_name
            }
        except Exception as e:
            # In case of any unexpected win32 API failure
            return {"title": "", "process": "", "error": str(e)}

if __name__ == "__main__":
    import time
    sensor = WindowSensor()
    while True:
        info = sensor.get_active_window_info()
        print(f"Active: {info.get('process')} - {info.get('title')}")
        time.sleep(1)