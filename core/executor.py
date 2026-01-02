import subprocess
import os

class WEExecutor:
    def __init__(self, we_path):
        self.we_path = we_path
        if not os.path.exists(self.we_path):
            raise FileNotFoundError(f"Wallpaper Engine executable not found at: {self.we_path}")

    def _run_command(self, args):
        """Runs a command silently."""
        cmd = [self.we_path, "-control"] + args
        try:
            # Use CREATE_NO_WINDOW to avoid popping up cmd windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"Executed: {' '.join(cmd)}")
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")

    def open_playlist(self, playlist_name):
        self._run_command(["openPlaylist", "-playlist", playlist_name])

    def next_wallpaper(self):
        self._run_command(["nextWallpaper"])
