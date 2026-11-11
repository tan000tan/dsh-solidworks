import sys
import time
import win32gui
import win32process
import win32con

target_pids = {3180, 5108, 11380}
hwnds = []

def enum_cb(hwnd, extra):
    if win32gui.IsWindow(hwnd):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in target_pids:
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            print(f"Found HWND {hwnd} for PID {pid}: title='{title}', class='{cls}'")
            hwnds.append((hwnd, pid))
    return True

win32gui.EnumWindows(enum_cb, None)
for hwnd, pid in hwnds:
    print(f"Sending WM_CLOSE to HWND {hwnd} (PID {pid})...")
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

time.sleep(3)
print("Finished graceful close message dispatch.")
