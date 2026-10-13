import time
import os
import sys
import datetime
import threading
import ctypes
import ctypes.wintypes
import win32gui
import win32process
import psutil
import pyautogui
import mss
import win32ui
import pystray
import pytesseract
from PIL import Image, ImageDraw
from database import SessionLocal, Activity
from config import BASE_DIR, get_images_path, load_config

# Global state
is_recording = True
is_idle = False
is_manually_paused = False
tray_icon = None

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
    """Create a 64x64 circle icon with the given color."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline=(255, 255, 255, 200),
        width=2
    )
    return img

def update_tray_icon():
    """Update the tray icon based on current state."""
    global tray_icon
    if tray_icon is None:
        return
    if is_manually_paused:
        tray_icon.icon = create_icon_image((244, 67, 54))  # Red - manually paused
        tray_icon.title = "Recollect - Paused"
    elif is_idle:
        tray_icon.icon = create_icon_image((255, 152, 0))  # Orange - idle
        tray_icon.title = "Recollect - Idle"
    else:
        tray_icon.icon = create_icon_image((76, 175, 80))  # Green - recording
        tray_icon.title = "Recollect - Recording"

def toggle_recording(icon, item):
    """Toggle recording state from the tray menu."""
    global is_manually_paused
    is_manually_paused = not is_manually_paused
    update_tray_icon()
    state = "Paused" if is_manually_paused else "Recording"
    print(f"[Tray] {state}")

def quit_app(icon, item):
    """Quit the application from the tray menu."""
    print("[Tray] Quitting...")
    icon.stop()
    os._exit(0)

def get_app_icon(pid, icons_dir=None):
    """Extract the icon from the application's executable and save it."""
    try:
        icons_dir = icons_dir or BASE_DIR / "icons"
        if not os.path.exists(icons_dir):
            os.makedirs(icons_dir, exist_ok=True)
            
        process = psutil.Process(pid)
        exe_path = process.exe()
        app_name = process.name()
        
        icon_filename = f"{app_name}.png"
        icon_path = os.path.join(icons_dir, icon_filename)
        
        # If we already have the icon for this app, return it
        if os.path.exists(icon_path) and os.path.getsize(icon_path) > 0:
            return icon_path
            
        # Extract icons
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        
        if not large:
            # Try to get it from the window handle if no exe icon found
            for h in small:
                win32gui.DestroyIcon(h)
            return None
            
        # Use the first large icon
        hicon = large[0]
        
        # Clean up others
        for h in large[1:]: win32gui.DestroyIcon(h)
        for h in small: win32gui.DestroyIcon(h)
        
        info = win32gui.GetIconInfo(hicon)
        hbmMask = info[3]
        hbmColor = info[4]
        
        if hbmColor:
            # We have a color bitmap
            try:
                bmp = win32ui.CreateBitmapFromHandle(hbmColor)
                bmpinfo = bmp.GetInfo()
                bmpstr = bmp.GetBitmapBits(True)
                
                # Create image
                if bmpinfo['bmBitsPixel'] == 32:
                    img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)
                else:
                    img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
                
                # Some icons have fully zero alpha channel. Check and fix it.
                if bmpinfo['bmBitsPixel'] == 32:
                    alphas = img.split()[3]
                    if not alphas.getbbox():
                        # Entirely transparent, fallback to RGB
                        img = img.convert('RGB')
                        
                img.thumbnail((32, 32), Image.Resampling.LANCZOS)
                img.save(icon_path)
            finally:
                pass
        
        # Cleanup
        win32gui.DeleteObject(hbmMask)
        if hbmColor:
            win32gui.DeleteObject(hbmColor)
        win32gui.DestroyIcon(hicon)
        
        return icon_path
    except Exception as e:
        print(f"Error extracting icon: {e}")
        return None

def get_active_window_info():
    try:
        window = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(window)
        _, pid = win32process.GetWindowThreadProcessId(window)
        
        if pid > 0:
            process = psutil.Process(pid)
            app_name = process.name()
        else:
            app_name = "Unknown"
            pid = 0
        return title, app_name, pid
    except Exception as e:
        print(f"Error getting window info: {e}")
        return "Unknown", "Unknown", 0

def wait_for_capture_trigger(app_name, window_title, interval):
    """Wait for the normal capture interval or an active window change."""
    deadline = time.monotonic() + interval

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return

        time.sleep(min(1, remaining))

        cfg = load_config()
        if cfg.get("is_paused", False) or is_manually_paused:
            return

        current_title, current_app_name, _ = get_active_window_info()
        if current_app_name != app_name or current_title != window_title:
            return

def record_activity():
    """Background recording loop that runs in a separate thread."""
    global is_idle
    
    with mss.MSS() as sct:
        while True:
            # Check config for pause state
            cfg = load_config()
            is_paused_config = cfg.get("is_paused", False)
            
            if is_paused_config or is_manually_paused:
                time.sleep(1)
                continue

            # Check idle state
            auto_pause = cfg.get("auto_pause_on_idle", True)
            interval = cfg.get("screenshot_interval", 60)
            
            currently_idle = False
            if auto_pause:
                idle_seconds = get_idle_duration_seconds()
                if idle_seconds >= interval:
                    currently_idle = True
                    if not is_idle:
                        is_idle = True
                        update_tray_icon()
                        print(f"[Idle] User idle for {idle_seconds:.0f}s, logging idle state...")
                else:
                    if is_idle:
                        is_idle = False
                        update_tray_icon()
                        print("[Idle] User active again, resuming recording...")
            elif is_idle:
                is_idle = False
                update_tray_icon()

            window_title, app_name, _ = get_active_window_info()

            try:
                if currently_idle:
                    # Log an Idle entry without screenshot
                    with SessionLocal() as db:
                        db.add(Activity(
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                            image_path=None,
                            app_name="System Idle",
                            window_title="System Idle",
                            url=None,
                            mouse_x=0,
                            mouse_y=0,
                            is_idle=True,
                            icon_path=None,
                            interval_at_capture=interval,
                            ocr_text=None
                        ))
                        db.commit()
                    time.sleep(interval)
                    continue

                # --- ACTIVE RECORDING ---
                images_dir = get_images_path(cfg)
                images_dir.mkdir(parents=True, exist_ok=True)

                # 1. Timestamps & Paths
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                image_filename = f"{timestamp_str}.webp" 
                image_path = images_dir / image_filename
                
                # 2. Take screenshot of the monitor containing the mouse
                mouse_x, mouse_y = pyautogui.position()
                sct_img = None
                
                for monitor in sct.monitors[1:]:
                    if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
                        monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
                        sct_img = sct.grab(monitor)
                        break
                
                if sct_img is None:
                    sct_img = sct.grab(sct.monitors[1])
                    
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                # Keep the current visual quality while using WebP's strongest
                # encoder effort. This reduces file size without resizing or
                # lowering the quality setting.
                img.save(image_path, "WEBP", quality=80, method=6)
                
                # 3. Get active window info
                window_title, app_name, pid = get_active_window_info()
                
                # 3.5 Get app icon
                icon_path = None
                if pid > 0:
                    icon_path = get_app_icon(pid)
                
                # 5. Save to database
                new_activity = Activity(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    image_path=str(image_path),
                    app_name=app_name,
                    window_title=window_title,
                    url=None,
                    mouse_x=mouse_x,
                    mouse_y=mouse_y,
                    is_idle=False,
                    icon_path=icon_path,
                    interval_at_capture=interval,
                    ocr_text=None
                )

                # 6. Run OCR
                try:
                    new_activity.ocr_text = pytesseract.image_to_string(img)
                except Exception as ocr_e:
                    print(f"OCR Error: {ocr_e}")

                with SessionLocal() as db:
                    db.add(new_activity)
                    db.commit()
                
                print(f"[{timestamp_str}] Recorded {app_name} - {window_title}")
                
            except Exception as e:
                print(f"Error during recording: {e}")
            
            wait_for_capture_trigger(app_name, window_title, interval)

def setup_tray():
    """Set up and run the system tray icon."""
    global tray_icon

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: "Resume" if is_manually_paused else "Pause",
            toggle_recording
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app)
    )

    tray_icon = pystray.Icon(
        "Recollect",
        create_icon_image((76, 175, 80)),  # Start with green
        "Recollect - Recording",
        menu
    )

    tray_icon.run()

if __name__ == "__main__":
    print("Starting Recollect recorder...")
    
    no_tray = "--no-tray" in sys.argv

    # Start the recording loop in a background thread
    recorder_thread = threading.Thread(target=record_activity, daemon=True)
    recorder_thread.start()

    if no_tray:
        # Keep the main thread alive since we don't have a tray icon to do it
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        # Run the tray icon in the main thread (required for Windows GUI)
        setup_tray()
