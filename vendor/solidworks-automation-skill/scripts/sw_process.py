"""@brief 只读枚举 SolidWorks PID 与可识别版本；支持多实例元数据与窗口标题检测。"""
import ctypes
from ctypes import wintypes
import os


def get_instance_window_title(pid: int) -> str:
    """获取指定 PID 的主窗口标题，未找到或失败返回空字符串。"""
    if os.name != "nt":
        return ""
    
    user32 = ctypes.windll.user32
    found_title = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if "solidworks" in title.lower():
                    found_title.append(title)
                    return False  # stop enumeration
        return True

    cb = WNDENUMPROC(enum_proc)
    user32.EnumWindows(cb, 0)
    return found_title[0] if found_title else ""


def is_instance_responding(pid: int) -> bool:
    """检测指定 PID 的主窗口是否处于响应状态（避免与假死/模态弹窗挂起的实例死锁）。"""
    if os.name != "nt":
        return True
    
    user32 = ctypes.windll.user32
    is_hung = False

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd, lparam):
        nonlocal is_hung
        if not user32.IsWindowVisible(hwnd):
            return True
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            if hasattr(user32, "IsHungAppWindow"):
                if user32.IsHungAppWindow(hwnd):
                    is_hung = True
                    return False
        return True

    cb = WNDENUMPROC(enum_proc)
    user32.EnumWindows(cb, 0)
    return not is_hung


def list_solidworks_instances():
    """
    返回系统中所有运行的 SolidWorks 实例的详细信息列表。
    每个条目包含：pid, year, path, window_title, responding, is_active
    """
    if os.name != "nt":
        return []

    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
            ("name", wintypes.WCHAR * 260)
        ]

    api = ctypes.windll.kernel32
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    api.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    api.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]

    snapshot = api.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return []

    instances = []
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)

    try:
        valid = api.Process32FirstW(snapshot, ctypes.byref(entry))
        while valid:
            if entry.name.casefold() == "sldworks.exe":
                pid = int(entry.pid)
                year = None
                exe_path = ""
                handle = api.OpenProcess(0x1000, False, pid)
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        if api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                            exe_path = buffer.value
                            try:
                                import win32api
                                version_info = win32api.GetFileVersionInfo(exe_path, "\\")
                                major = version_info["FileVersionMS"] >> 16
                                year = major if 2000 <= major <= 2035 else major + 1992 if 18 <= major <= 43 else None
                            except Exception:
                                pass
                    except Exception:
                        pass
                    finally:
                        api.CloseHandle(handle)

                title = get_instance_window_title(pid)
                responding = is_instance_responding(pid)

                instances.append({
                    "pid": pid,
                    "year": year,
                    "exe_path": exe_path,
                    "window_title": title,
                    "responding": responding
                })
            valid = api.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        api.CloseHandle(snapshot)

    return instances


def solidworks_processes():
    """@brief 保持向后兼容：返回 PID→年份；枚举失败返回 None，避免猜测进程所有权。"""
    instances = list_solidworks_instances()
    if not instances and os.name == "nt":
        # Check snapshot failure vs 0 processes
        api = ctypes.windll.kernel32
        snapshot = api.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return None
        api.CloseHandle(snapshot)
    return {inst["pid"]: inst["year"] for inst in instances}
