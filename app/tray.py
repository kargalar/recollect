import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import subprocess
import webbrowser
import sys
import os
import time
import threading
import ctypes
import ctypes.wintypes
from config import BASE_DIR, get_images_path, load_config, save_config

# Global state
is_paused = False
is_idle = False
icon = None
recorder_process = None
api_process = None
_instance_mutex_handle = None

SINGLE_INSTANCE_MUTEX_NAME = "Local\\Recollect.Tray.SingleInstance"


def acquire_single_instance():
    """Keep only one tray application running in the current Windows session."""
    global _instance_mutex_handle
    if os.name != "nt":
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    create_mutex.restype = ctypes.wintypes.HANDLE

    ctypes.set_last_error(0)
    mutex_handle = create_mutex(None, True, SINGLE_INSTANCE_MUTEX_NAME)
    if not mutex_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(mutex_handle)
        return False

    _instance_mutex_handle = mutex_handle
    return True

# Windows API for idle detection
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]

def get_idle_duration_seconds():
    """Get the number of seconds since the last user input (keyboard/mouse)."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0

def create_icon_image(color):
    """Draw Recollect's simple memory-ring tray icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(43, 43, 43))
    draw.ellipse([13, 13, 51, 51], outline=color, width=4)
    draw.ellipse([27, 27, 37, 37], fill=(245, 247, 250))
    draw.line([32, 15, 46, 15, 46, 27], fill=(245, 247, 250), width=4)
    return img

def update_icon_ui():
    """Update the icon and title based on current state."""
    global icon, is_paused, is_idle
    if not icon:
        return
        
    if is_paused:
        icon.icon = create_icon_image((244, 67, 54))  # Red - Paused
        icon.title = "Recollect - Paused"
    elif is_idle:
        icon.icon = create_icon_image((255, 152, 0))  # Orange - Idle
        icon.title = "Recollect - Idle"
    else:
        icon.icon = create_icon_image((76, 175, 80))  # Green - Recording
        icon.title = "Recollect - Recording"

def state_monitor_thread():
    """Background thread to monitor idle state and config changes."""
    global is_idle, is_paused, icon
    while True:
        if icon:
            cfg = load_config()
            new_is_paused = cfg.get("is_paused", False)
            auto_pause = cfg.get("auto_pause_on_idle", True)
            interval = cfg.get("screenshot_interval", 60)
            
            new_is_idle = False
            if auto_pause:
                idle_seconds = get_idle_duration_seconds()
                if idle_seconds >= interval:
                    new_is_idle = True
            
            if new_is_idle != is_idle or new_is_paused != is_paused:
                is_idle = new_is_idle
                is_paused = new_is_paused
                update_icon_ui()
        
        time.sleep(2)

def on_open(icon, item):
    webbrowser.open('http://localhost:8000')

def open_images_folder(icon, item):
    cfg = load_config()
    images_path = get_images_path(cfg)
    images_path.mkdir(parents=True, exist_ok=True)
    os.startfile(images_path)

def toggle_pause(icon, item):
    global is_paused
    cfg = load_config()
    current_state = cfg.get("is_paused", False)
    cfg["is_paused"] = not current_state
    if save_config(cfg):
        is_paused = not current_state
        update_icon_ui()

def on_quit(icon, item):
    icon.stop()
    # Terminate subprocesses
    try:
        if recorder_process:
            recorder_process.terminate()
        if api_process:
            api_process.terminate()
    except Exception as e:
        print(f"Error terminating processes: {e}")
    os._exit(0)

if __name__ == '__main__':
    if not acquire_single_instance():
        sys.exit(0)

    # Determine paths
    base_dir = BASE_DIR
    venv_python = base_dir / "venv" / "Scripts" / "pythonw.exe"
    if not os.path.exists(venv_python):
        venv_python = base_dir / "venv" / "Scripts" / "python.exe"
        
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    if getattr(sys, "frozen", False):
        recorder_command = [base_dir / "RecollectRecorder.exe", "--no-tray"]
        api_command = [base_dir / "RecollectApi.exe"]
    else:
        recorder_command = [venv_python, "recorder.py", "--no-tray"]
        api_command = [venv_python, "-m", "uvicorn", "main:app", "--port", "8000"]
    
    # Start the recorder with --no-tray flag
    CREATE_NO_WINDOW = 0x08000000
    
    recorder_process = subprocess.Popen(
        recorder_command,
        cwd=base_dir,
        creationflags=CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    api_process = subprocess.Popen(
        api_command,
        cwd=base_dir,
        creationflags=CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Set up the tray icon
    initial_color = (76, 175, 80) # Default green
    cfg = load_config()
    if cfg.get("is_paused", False):
        initial_color = (244, 67, 54) # Red
        is_paused = True

    menu = pystray.Menu(
        item('Open Web UI', on_open),
        item('Open Screenshots Folder', open_images_folder),
        item(
            lambda item: "Resume Recording" if is_paused else "Pause Recording", 
            toggle_pause
        ),
        pystray.Menu.SEPARATOR,
        item('Quit', on_quit)
    )
    
    icon = pystray.Icon("Recollect", create_icon_image(initial_color), "Recollect", menu)
    
    # Start monitoring thread
    monitor = threading.Thread(target=state_monitor_thread, daemon=True)
    monitor.start()
    
    # Run the tray icon application
    icon.run()
