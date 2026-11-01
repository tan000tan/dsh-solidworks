"""
SolidWorks 连接工具
提供连接到 SolidWorks 实例的各种方法
"""
import glob
import json
import os
import queue
import tempfile
import threading
import time
from pathlib import Path
try:
    from .sw_file_load import SolidWorksDocumentOpenError, classify_sw_file_load_errors, classify_sw_file_load_warnings
except ImportError:
    from sw_file_load import SolidWorksDocumentOpenError, classify_sw_file_load_errors, classify_sw_file_load_warnings

try:
    from .sw_preflight import ensure_solidworks_installed, import_com_dependencies
except ImportError:
    from sw_preflight import ensure_solidworks_installed, import_com_dependencies

pythoncom, win32com_client, VARIANT = import_com_dependencies()
try:
    from .sw_process import solidworks_processes
except ImportError:
    from sw_process import solidworks_processes


DOC_TYPE_MAP = {
    "part": 1,
    "prt": 1,
    "sldprt": 1,
    "assembly": 2,
    "asm": 2,
    "sldasm": 2,
    "drawing": 3,
    "drw": 3,
    "slddrw": 3,
}

DOC_TYPE_LABELS = {
    "part": "零件",
    "assembly": "装配体",
    "drawing": "工程图",
}

DEFAULT_TEMPLATE_PREFS = {
    "part": 8,       # swUserPreferenceStringValue_e.swDefaultTemplatePart
    "assembly": 9,   # swUserPreferenceStringValue_e.swDefaultTemplateAssembly
    "drawing": 10,   # swUserPreferenceStringValue_e.swDefaultTemplateDrawing
}

SW_ALWAYS_USE_DEFAULT_TEMPLATES = 111


class SolidWorksConnectionError(RuntimeError):
    """带阶段和错误码的 SolidWorks 连接错误。"""

    def __init__(self, code, stage, message):
        self.code = code
        self.stage = stage
        super().__init__(f"[{code}] {stage}: {message}")


class _LaunchGuard:
    """跨进程启动互斥；Windows 使用命名 Mutex，其它平台使用独占锁文件。"""

    def __init__(self, name="CADStudio.SolidWorks.Launch"):
        self.name = name
        self.handle = None
        self.path = Path(tempfile.gettempdir()) / "cad-studio-solidworks-launch.lock"
        self._owns_file = False

    def __enter__(self):
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            from ctypes import wintypes
            kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            if not self.handle:
                raise SolidWorksConnectionError("SW_MUTEX", "locking", "无法创建 SolidWorks 启动互斥锁")
            wait_result = kernel32.WaitForSingleObject(self.handle, 15000)
            if wait_result not in (0, 0x80):
                kernel32.CloseHandle(self.handle)
                self.handle = None
                raise SolidWorksConnectionError("SW_MUTEX_TIMEOUT", "locking", "等待其它启动任务超时")
            return self

        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            self._owns_file = True
        except FileExistsError as exc:
            try:
                stale_pid = int(self.path.read_text(encoding="ascii").strip())
                os.kill(stale_pid, 0)
            except (ProcessLookupError, ValueError):
                self.path.unlink(missing_ok=True)
                return self.__enter__()
            raise SolidWorksConnectionError("SW_MUTEX_BUSY", "locking", "已有 SolidWorks 启动任务") from exc
        return self

    def __exit__(self, *_):
        if os.name == "nt" and self.handle:
            import ctypes

            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
        elif self._owns_file:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._owns_file = False


_MEMBER_UNSET = object()


def _raw_get_com_member(obj, attr_name, *args, default=_MEMBER_UNSET):
    try:
        member = getattr(obj, attr_name)
    except AttributeError:
        if default is not _MEMBER_UNSET:
            return default
        raise
    if args:
        return member(*args)
    try:
        return member() if callable(member) else member
    except Exception as exc:
        message = str(exc)
        if "-2147352573" in message or "找不到成员" in message or "Member not found" in message:
            return member
        raise


def get_com_member(obj, attr_name, *args, default=_MEMBER_UNSET):
    """
    兼容 pywin32 中“同一成员在不同环境下可能是属性也可能是方法”的情况。
    支持在跨桌面/非默认桌面环境下自动路由到 STA Worker 线程中执行。
    """
    try:
        from .sw_connect import _global_sta_worker
    except Exception:
        try:
            from sw_connect import _global_sta_worker
        except Exception:
            _global_sta_worker = globals().get("_global_sta_worker")

    worker = _global_sta_worker if "_global_sta_worker" in globals() else None
    if worker and threading.current_thread() != worker._thread:
        try:
            return worker.execute(lambda: _raw_get_com_member(obj, attr_name, *args, default=default))
        except Exception:
            pass
    return _raw_get_com_member(obj, attr_name, *args, default=default)


def safe_get_com_member(obj, attr_name, *args):
    """
    读取 COM 成员，兼容 pywin32 中伪可调用属性。

    保留该别名便于其它模块表达“安全读取”的意图；核心逻辑统一在 get_com_member。
    """
    return get_com_member(obj, attr_name, *args)


def create_empty_dispatch_variant():
    """创建可传给 COM 接口的空 Dispatch 参数。"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def normalize_doc_type(doc_type):
    """
    规范化文档类型名称。

    参数:
        doc_type: "part"、"assembly"、"drawing" 或常见缩写/扩展名

    返回:
        (name, enum_value) 元组
    """
    key = str(doc_type).strip().lower().lstrip(".")
    enum_value = DOC_TYPE_MAP.get(key)
    if enum_value is None:
        raise ValueError(f"未知文档类型: {doc_type}")

    name_map = {1: "part", 2: "assembly", 3: "drawing"}
    return name_map[enum_value], enum_value


def _expand_path(file_path):
    """展开用户目录和环境变量，并返回绝对路径。"""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(file_path)))


def _ensure_parent_dir(file_path):
    """确保输出文件的父目录存在。"""
    parent = os.path.dirname(_expand_path(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _prog_id_for_version(version):
    """返回 SolidWorks 年份对应的 ProgID。"""
    if version is None:
        return "SldWorks.Application"
    try:
        year = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SolidWorks 版本必须是年份，例如 2024: {version}") from exc
    if year < 2010 or year > 2035:
        raise ValueError(f"不支持的 SolidWorks 版本年份: {year}")
    return f"SldWorks.Application.{(year - 2000) + 8}"


def _read_active_document(sw):
    """读取活动文档，兼容 COM 属性/方法差异。"""
    try:
        return get_com_member(sw, "ActiveDoc", default=None)
    except Exception:
        return None


def _wait_until_ready(sw, timeout_seconds):
    """等待 COM 服务器可读，避免固定 sleep 导致 UI 假死。"""
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    last_error = None
    try:
        worker = get_sta_worker()
    except Exception:
        worker = None
    while time.monotonic() < deadline:
        try:
            if worker and threading.current_thread() != worker._thread:
                worker.execute(lambda: get_com_member(sw, "RevisionNumber"))
            else:
                get_com_member(sw, "RevisionNumber")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise SolidWorksConnectionError(
        "SW_START_TIMEOUT", "ready", f"SolidWorks 启动超时（{timeout_seconds:.1f}s）: {last_error or 'COM 未就绪'}"
    )


def close_owned_solidworks(sw, started_by_cad_studio, expected_pid=None):
    """只退出由当前 CAD Studio 会话启动的 SolidWorks 实例。"""
    if not started_by_cad_studio:
        return False
    if expected_pid is not None:
        try:
            if int(get_com_member(sw, "GetProcessID")) != int(expected_pid):
                return False
        except Exception:
            return False
    for member_name in ("ExitApp", "Quit"):
        try:
            member = getattr(sw, member_name)
            member() if callable(member) else None
            return True
        except Exception:
            continue
    return False


def _is_default_desktop():
    """检查当前线程所在 Windows 桌面是否为交互式 Default 桌面。"""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hdesk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        name_buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        if user32.GetUserObjectInformationW(hdesk, 2, name_buf, ctypes.sizeof(name_buf), ctypes.byref(needed)):
            return name_buf.value.lower() == "default"
    except Exception:
        pass
    return False


class TaskState:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"


class WorkerTask:
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.state = TaskState.QUEUED
        self.result_queue = queue.Queue(maxsize=1)
        self.lock = threading.Lock()


class DesktopPinnedStaWorker:
    """
    Dedicated STA Worker thread permanently pinned to the Windows interactive 'Default' desktop.

    Architecture guarantees:
    1. Single-Threaded Apartment (STA) model compliance for SolidWorks Out-of-Process COM server.
    2. Zero cross-thread COM interface marshaling degradation (avoids RPC_E_WRONG_THREAD).
    3. Strict SetThreadDesktop timing (called BEFORE any window creation and BEFORE CoInitialize).
    4. Safe PyHDESK handle lifecycle (avoids Double Free crash by relying on Python dealloc).
    5. Clean message pump during idle wait only (eliminates COM reentrancy during modeling).
    6. Task timeout state machine: discards queued tasks that timed out prior to worker pickup.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._running = False
        self._thread = None
        self._hdesk = None
        self._ready_event = threading.Event()
        self._init_error = None
        self._desktop_name = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._ready_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="DSH-SolidWorks-STAWorker",
            daemon=True,
        )
        self._thread.start()
        if not self._ready_event.wait(timeout=10.0):
            raise RuntimeError("DesktopPinnedStaWorker startup timed out")
        if self._init_error:
            raise RuntimeError(f"DesktopPinnedStaWorker startup failed: {self._init_error}")

    def _worker_loop(self):
        if os.name == "nt":
            try:
                import ctypes
                import win32con
                import win32service

                # Open Default desktop and pin thread before creating any window or initializing COM
                self._hdesk = win32service.OpenDesktop("Default", 0, False, win32con.MAXIMUM_ALLOWED)
                if not ctypes.windll.user32.SetThreadDesktop(int(self._hdesk)):
                    # Note error but proceed if already default
                    err = ctypes.GetLastError()
                    if not _is_default_desktop():
                        self._init_error = f"SetThreadDesktop failed with code {err}"
            except Exception as exc:
                if not _is_default_desktop():
                    self._init_error = f"OpenDesktop/SetThreadDesktop error: {exc}"

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception as exc:
            self._init_error = f"CoInitialize error: {exc}"
            self._ready_event.set()
            return

        self._ready_event.set()

        while self._running:
            try:
                task = self._queue.get(timeout=0.05)
                if task is None:
                    break
                with task.lock:
                    if task.state == TaskState.TIMED_OUT:
                        continue
                    task.state = TaskState.RUNNING

                try:
                    res = task.func(*task.args, **task.kwargs)
                    with task.lock:
                        task.state = TaskState.COMPLETED
                    task.result_queue.put((True, res))
                except Exception as exc:
                    with task.lock:
                        task.state = TaskState.FAILED
                    task.result_queue.put((False, exc))
            except queue.Empty:
                if os.name == "nt":
                    try:
                        import pythoncom
                        pythoncom.PumpWaitingMessages()
                    except Exception:
                        pass

        # Cleanup on exit
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def execute(self, func, *args, timeout=None, **kwargs):
        if not self._running:
            self.start()

        # If already executing inside the STA worker thread, execute directly
        if threading.current_thread() == self._thread:
            return func(*args, **kwargs)

        task = WorkerTask(func, args, kwargs)
        self._queue.put(task)

        try:
            success, val = task.result_queue.get(timeout=timeout)
        except queue.Empty:
            with task.lock:
                if task.state == TaskState.QUEUED:
                    task.state = TaskState.TIMED_OUT
            raise TimeoutError(f"SolidWorks COM operation timed out after {timeout}s")

        if success:
            return val
        raise val

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


_global_sta_worker = None
_global_sta_lock = threading.Lock()


def get_sta_worker():
    """Returns singleton DesktopPinnedStaWorker."""
    global _global_sta_worker
    if _global_sta_worker is None:
        with _global_sta_lock:
            if _global_sta_worker is None:
                import atexit
                worker = DesktopPinnedStaWorker()
                worker.start()
                atexit.register(worker.stop)
                _global_sta_worker = worker
    return _global_sta_worker


def get_final_path(target_path):
    """
    Resolve final physical path on disk using Windows Native GetFinalPathNameByHandle,
    properly expanding Directory Junctions, Symlinks, and uncreated child paths.
    """
    if os.name != "nt":
        return os.path.abspath(str(target_path))
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        kernel32.GetFinalPathNameByHandleW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        cur = os.path.abspath(str(target_path))
        tail = []
        while not os.path.exists(cur):
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            tail.append(os.path.basename(cur))
            cur = parent

        if os.path.exists(cur):
            handle = kernel32.CreateFileW(
                cur,
                0,
                1 | 2,  # FILE_SHARE_READ | FILE_SHARE_WRITE
                None,
                3,  # OPEN_EXISTING
                0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
                None,
            )
            if handle is not None and handle not in (-1, 0, 0xFFFFFFFFFFFFFFFF):
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    res = kernel32.GetFinalPathNameByHandleW(handle, buf, 1024, 0)
                    if res > 0:
                        real = buf.value
                        if real.startswith("\\\\?\\UNC\\") or real.startswith("\\\\?\\UNC/"):
                            real = "\\\\" + real[8:]
                        elif real.startswith("\\\\?\\"):
                            real = real[4:]
                        for part in reversed(tail):
                            real = os.path.join(real, part)
                        return os.path.abspath(real)
                finally:
                    kernel32.CloseHandle(handle)
    except Exception:
        pass
    return os.path.abspath(str(target_path))


def get_default_workspace():
    """
    Resolve default user workspace root respecting Windows 10/11 OneDrive redirection.
    """
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            personal, _ = winreg.QueryValueEx(key, "Personal")
            winreg.CloseKey(key)
            if personal:
                expanded = os.path.expandvars(personal)
                return os.path.join(expanded, "DSH-SolidWorks-Workspace")
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~/Documents"), "DSH-SolidWorks-Workspace")


def validate_path_against_allowed_roots(target_path, allowed_roots=None):
    """
    Python-layer defense-in-depth: validates target_path against allowed roots.
    Fails closed if target_path falls outside or if roots are empty under DSH environment.
    """
    if not target_path:
        return True

    env_roots = os.environ.get("DSH_ALLOWED_ROOTS")
    is_dsh_env = env_roots is not None
    if is_dsh_env and allowed_roots is None:
        try:
            allowed_roots = json.loads(env_roots)
        except Exception:
            allowed_roots = []

    # If allowed_roots was explicitly passed or configured via DSH_ALLOWED_ROOTS
    if allowed_roots is not None:
        if not allowed_roots:
            return False  # Fail-closed when roots list is configured but empty
        final_target = get_final_path(target_path).lower()
        for root in allowed_roots:
            if not root:
                continue
            final_root = get_final_path(root).lower()
            try:
                rel = os.path.relpath(final_target, final_root)
                if not rel.startswith("..") and not os.path.isabs(rel):
                    return True
            except ValueError:
                continue
        return False

    # Standalone script execution without explicit DSH sandbox boundary
    return True


def _get_active_object(prog_id):
    """
    获取活动 COM 对象，支持 Windows 跨桌面/沙箱穿透。
    通过常驻 DesktopPinnedStaWorker 在 Default 桌面与 STA 环境下稳定挂接。
    """
    worker = get_sta_worker()
    if threading.current_thread() == worker._thread:
        return win32com_client.GetActiveObject(prog_id)
    return worker.execute(lambda: win32com_client.GetActiveObject(prog_id))


def connect_solidworks(version=None, wait_seconds=5, visible=True, return_metadata=False):
    """
    连接到 SolidWorks 实例。

    参数:
        version: SolidWorks 版本年份（如 2024），None 则自动检测
        wait_seconds: 启动新实例后等待秒数
        visible: 启动新实例后是否显示窗口

    返回:
        (sw, model) 元组，model 可能为 None（无打开的文档时）
    """
    ensure_solidworks_installed()
    prog_id = _prog_id_for_version(version)
    sw = None
    launched_here = False
    dispatched = False

    # 启动和附着共享同一把互斥锁，避免多个 worker 同时拉起实例。
    with _LaunchGuard():
        before = solidworks_processes()
        try:
            sw = _get_active_object(prog_id)
            print(f"已连接到运行中的 SolidWorks 实例（ProgID: {prog_id}）")
        except Exception as attach_error:
            try:
                if before is None:
                    raise SolidWorksConnectionError("SW_PROCESS_STATE_UNAVAILABLE", "attach", "无法读取 CAD 进程状态，已阻止不确定的启动")
                if before and (version is None or any(year is None or year == int(version) for year in before.values())):
                    # ROT 尚未注册时等待已有实例，禁止重复 Dispatch 启动同版本。
                    deadline = time.monotonic() + max(.1, float(wait_seconds))
                    while time.monotonic() < deadline:
                        try:
                            sw = _get_active_object(prog_id)
                            break
                        except Exception:
                            time.sleep(.1)
                    if sw is None:
                        try:
                            worker = get_sta_worker()
                            sw = worker.execute(lambda: win32com_client.Dispatch(prog_id))
                            dispatched = True
                        except Exception:
                            raise SolidWorksConnectionError("SW_INSTANCE_NOT_READY", "attach", "已有实例尚不可连接，已阻止重复启动")
                if sw is None:
                    sw = win32com_client.Dispatch(prog_id)
                    dispatched = True
                    try:
                        pid = int(get_com_member(sw, "GetProcessID"))
                        launched_here = before is not None and pid > 0 and pid not in before
                    except Exception:
                        launched_here = False
                try:
                    sw.Visible = visible
                except Exception:
                    pass
                print(f"已连接 SolidWorks（ProgID: {prog_id}）")
                _wait_until_ready(sw, wait_seconds)
            except SolidWorksConnectionError:
                close_owned_solidworks(sw, launched_here)
                raise
            except Exception as launch_error:
                close_owned_solidworks(sw, launched_here)
                raise SolidWorksConnectionError(
                    "SW_LAUNCH_FAILED", "launch", f"无法启动 {prog_id}: {launch_error}; attach={attach_error}"
                ) from launch_error

        _wait_until_ready(sw, wait_seconds)
        if dispatched and before is not None:
            pid = int(get_com_member(sw, "GetProcessID"))
            launched_here = pid > 0 and pid not in before
        actual = get_sw_version(sw)
        if version is not None and actual["year"] != int(version):
            close_owned_solidworks(sw, launched_here)
            raise SolidWorksConnectionError("SW_VERSION_MISMATCH", "verify", f"请求 {version}，实际连接 {actual['year']}")

    if sw is None:
        raise SolidWorksConnectionError("SW_NO_INSTANCE", "connect", "未获得 SolidWorks COM 实例")

    model = _read_active_document(sw)
    if model:
        doc_types = {1: "零件", 2: "装配体", 3: "工程图"}
        doc_type = get_com_member(model, "GetType")
        title = get_com_member(model, "GetTitle")
        print(f"当前文档: {title} (类型: {doc_types.get(doc_type, '未知')})")
    else:
        print("当前没有打开的文档")

    metadata = {
        "prog_id": prog_id,
        "requested_version": int(version) if version is not None else None,
        "started_by_cad_studio": launched_here,
        "actual_version": actual["year"],
        "actual_revision": actual["revision"],
        "process_id": get_com_member(sw, "GetProcessID", default=None),
    }
    return (sw, model, metadata) if return_metadata else (sw, model)


def get_sw_version(sw):
    """获取 SolidWorks 版本信息。"""
    rev = get_com_member(sw, "RevisionNumber")
    major = int(rev.split(".")[0])
    year = major - 8 + 2000
    return {"revision": rev, "year": year, "major": major}


def find_template(sw, doc_type="part"):
    """
    自动查找 SolidWorks 文档模板。

    参数:
        sw: SolidWorks 应用对象
        doc_type: "part" | "assembly" | "drawing"

    返回:
        模板文件路径字符串
    """
    doc_type, _ = normalize_doc_type(doc_type)

    def _pref(key):
        try:
            return get_com_member(sw, "GetUserPreferenceStringValue", DEFAULT_TEMPLATE_PREFS[key])
        except Exception:
            return ""

    type_map = {
        "part": (_pref("part"), "*.prtdot"),
        "assembly": (_pref("assembly"), "*.asmdot"),
        "drawing": (_pref("drawing"), "*.drwdot"),
    }

    default_path, pattern = type_map.get(doc_type, type_map["part"])
    if default_path:
        for candidate_root in str(default_path).split(";"):
            candidate_root = _expand_path(candidate_root.strip().strip('"'))
            if not candidate_root:
                continue

            if os.path.isfile(candidate_root):
                return candidate_root

            if os.path.isdir(candidate_root):
                matches = glob.glob(os.path.join(candidate_root, pattern))
                if matches:
                    return matches[0]

    search_dirs = [
        r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\chinese-simplified",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english",
    ]
    for search_dir in search_dirs:
        matches = glob.glob(os.path.join(os.path.expandvars(search_dir), pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(f"无法找到 {doc_type} 模板文件，请手动指定路径")


def ensure_default_templates(sw):
    """
    @brief 配置默认模板并关闭新建文件模板选择提示。
    @param sw SolidWorks 应用对象。
    @return 字典，包含已确认的默认模板路径。
    """
    templates = {}
    for doc_type, preference in DEFAULT_TEMPLATE_PREFS.items():
        template_path = find_template(sw, doc_type)
        templates[doc_type] = template_path
        current_path = str(sw.GetUserPreferenceStringValue(preference) or "")
        if _expand_path(current_path) != _expand_path(template_path):
            sw.SetUserPreferenceStringValue(preference, template_path)
    try:
        sw.SetUserPreferenceToggle(SW_ALWAYS_USE_DEFAULT_TEMPLATES, True)
    except Exception as exc:
        print(f"提示: 无法设置始终使用默认模板: {exc}")
    return templates


def snapshot_open_documents(sw, *, strict=False):
    """
    快照当前已打开的文档标题集合。

    ISldWorks.GetDocuments 返回当前会话全部打开文档；部分版本在无文档时返回
    None 而非空数组。标题是判定"新建结果"的稳定标识，因为 NewDocument 成功后
    新文档尚未保存，GetPathName 为空字符串，无法用路径区分。
    """
    titles = set()
    try:
        documents = get_com_member(sw, "GetDocuments")
    except Exception as error:
        if strict:
            raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "documents", "无法读取打开文档清单，已阻止新建") from error
        return titles
    for document in documents or ():
        try:
            titles.add(str(get_com_member(document, "GetTitle")))
        except Exception as error:
            if strict:
                raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "documents", "无法确认已有文档身份，已阻止新建") from error
            continue
    return titles


def _find_new_document(sw, preexisting_titles):
    """
    在新建文档后定位真正的新文档。

    只返回标题不在 preexisting_titles 中的文档。绝不回退到裸 ActiveDoc：
    当 NewDocument 失败或返回 None 时，ActiveDoc 可能是用户先前打开的另一个
    文档，把它当作新建结果会让后续所有特征静默画到错误的文档上。
    """
    try:
        documents = get_com_member(sw, "GetDocuments")
    except Exception:
        return None
    for document in documents or ():
        try:
            title = str(get_com_member(document, "GetTitle"))
        except Exception:
            continue
        if title and title not in preexisting_titles:
            return document
    return None


def new_document(sw, doc_type="part", template_path=None, *, max_documents=None):
    """
    创建新文档。

    参数:
        sw: SolidWorks 应用对象
        doc_type: "part" | "assembly" | "drawing"
        template_path: 模板路径，None 则自动查找

    返回:
        新建的 IModelDoc2 对象

    异常:
        RuntimeError: 无法创建文档。此前的实现会在 NewDocument 返回 None 时
            盲取 sw.ActiveDoc，可能把用户已打开的文档误判为新建结果；现在改为
            按文档标题差集定位，定位不到就显式报错。
    """
    doc_type, _ = normalize_doc_type(doc_type)
    if not template_path:
        template_path = find_template(sw, doc_type)
    else:
        template_path = _expand_path(template_path)

    preexisting_titles = snapshot_open_documents(sw, strict=True)
    budget = int(max_documents if max_documents is not None else os.environ.get("SW_MAX_DOCUMENTS", "8"))
    if budget < 1 or len(preexisting_titles) >= budget:
        raise SolidWorksConnectionError("SW_DOCUMENT_BUDGET", "new_document", f"打开文档数已达预算 {budget}；请保存并关闭本轮文档")

    model = get_com_member(sw, "NewDocument", template_path, 0, 0, 0)
    if model is not None:
        # 正常路径：NewDocument 直接返回文档。仍需确认它确实是新文档，
        # 避免个别版本返回陈旧引用。
        try:
            if str(get_com_member(model, "GetTitle")) in preexisting_titles:
                model = None
        except Exception:
            pass

    if model is None:
        # 退化路径：NewDocument 返回 None 时，按标题差集轮询新文档。
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            model = _find_new_document(sw, preexisting_titles)
            if model is not None:
                break
            time.sleep(0.25)

    if model is None:
        raise RuntimeError(
            f"创建{DOC_TYPE_LABELS.get(doc_type, doc_type)}文档失败：SolidWorks 未返回新文档。"
            f"请确认模板可用（{template_path}）且未弹出模态对话框阻塞自动化。"
        )

    print(f"已创建新{DOC_TYPE_LABELS.get(doc_type, doc_type)}文档")
    return model


def open_document(sw, file_path, read_only=False, silent=False, raise_on_error=False):
    """
    打开已有文档。

    参数:
        sw: SolidWorks 应用对象
        file_path: 文件完整路径
        read_only: 是否以只读模式打开
        silent: 是否静默打开
        raise_on_error: 打开失败时是否抛出异常

    返回:
        IModelDoc2 对象
    """
    file_path = _expand_path(file_path)
    if not validate_path_against_allowed_roots(file_path):
        raise PermissionError(f"Access denied: path '{file_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")

    if not os.path.exists(file_path):
        message = f"文件不存在: {file_path}"
        if raise_on_error:
            raise FileNotFoundError(message)
        print(message)
        return None

    # 装配体会把组件文档加载到当前会话；再次 OpenDoc6 可能返回
    # swFileWithSameTitleAlreadyOpen。复用同一路径对象也能保留文档所有权。
    try:
        existing_model = sw.GetOpenDocumentByName(file_path)
    except Exception:
        existing_model = None
    if existing_model is not None:
        print(f"已复用打开文档: {file_path}")
        return existing_model

    ext = os.path.splitext(file_path)[1].lower()
    foreign_exts = {".step", ".stp", ".igs", ".iges"}
    type_map = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    options = 2 if read_only else 0  # swOpenDocOptions_ReadOnly = 2
    if silent:
        options |= 1  # swOpenDocOptions_Silent = 1

    if ext in foreign_exts:
        if read_only:
            print("提示: LoadFile4 导入外来 CAD 文件时不支持 read_only，已忽略该参数")
        if silent:
            print("提示: LoadFile4 导入外来 CAD 文件时不支持 OpenDoc6 silent 选项，已忽略该参数")
        ensure_default_templates(sw)
        import_data = sw.GetImportFileData(file_path)
        if import_data is None:
            message = f"获取导入数据失败: {file_path}"
            if raise_on_error:
                raise RuntimeError(message)
            print(message)
            return None
        # 非 DXF/DWG、非 Pro/E 外来文件应传 "r"，表示导入为新的 SolidWorks 文档；
        # 空字符串会在部分 SW2024 环境中弹出模板选择对话框并阻塞自动化。
        try:
            model = sw.LoadFile4(file_path, "r", import_data, errors)
        except TypeError:
            # SW2026 的 makepy 强类型代理会对 LoadFile4 的 [out] long
            # 再执行 int(VARIANT)，与 OpenDoc6 的已知问题相同。动态代理
            # 可以正确保留 by-ref 错误码，同时继续复用已取得的导入选项。
            ole_object = getattr(sw, "_oleobj_", None)
            if ole_object is None:
                raise
            dynamic_sw = win32com_client.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
            model = dynamic_sw.LoadFile4(file_path, "r", import_data, errors)
        warnings.value = 0
    else:
        doc_type = type_map.get(ext, 1)
        try:
            model = sw.OpenDoc6(file_path, doc_type, options, "", errors, warnings)
        except TypeError:
            # SW2024 的 makepy 强类型代理可能对 [out] long 再做 int(VARIANT)，
            # 动态代理会把显式 by-ref VARIANT 正确传给原生 OpenDoc6。
            ole_object = getattr(sw, "_oleobj_", None)
            if ole_object is None:
                raise
            dynamic_sw = win32com_client.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
            model = dynamic_sw.OpenDoc6(file_path, doc_type, options, "", errors, warnings)
        if isinstance(model, (tuple, list)):
            values = list(model)
            model = values[0] if values else None
            if len(values) > 1 and values[1] is not None:
                errors.value = int(values[1])
            if len(values) > 2 and values[2] is not None:
                warnings.value = int(values[2])
    if model:
        print(f"已打开: {file_path}")
    else:
        message = f"打开失败, 错误码: {errors.value} ({classify_sw_file_load_errors(errors.value)}), 警告码: {warnings.value} ({classify_sw_file_load_warnings(warnings.value)})"
        if raise_on_error:
            raise SolidWorksDocumentOpenError(message, errors.value, warnings.value)
        print(message)
    return model


def save_document(model, file_path=None):
    """
    保存文档。

    参数:
        model: IModelDoc2 对象
        file_path: 另存为路径，None 则保存到当前位置

    返回:
        bool 成功/失败
    """
    target_path = file_path
    if not target_path:
        try:
            target_path = get_com_member(model, 'GetPathName')
        except Exception:
            target_path = None

    if not target_path:
        print("保存失败: 未指定文件路径且文档尚未命名")
        return False

    target_path = _expand_path(target_path)
    if not validate_path_against_allowed_roots(target_path):
        raise PermissionError(f"Access denied: target path '{target_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")

    _ensure_parent_dir(target_path)
    save_code = get_com_member(model, "SaveAs3", target_path, 0, 1)
    success = (save_code == 0)

    if success:
        print(f"保存成功: {target_path}")
    else:
        print(f"保存失败, SaveAs3 错误码: {save_code}")
    return bool(success)


def mm(value):
    """毫米转米（SolidWorks API 单位）。"""
    return value / 1000.0


def deg(value):
    """角度转弧度。"""
    import math
    return value * math.pi / 180.0
