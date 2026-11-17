"""

SolidWorks 连接工具

提供连接到 SolidWorks 实例的各种方法

"""

import sys
if __name__ == "sw_connect" and "scripts.sw_connect" not in sys.modules:
    sys.modules["scripts.sw_connect"] = sys.modules[__name__]
elif __name__ == "scripts.sw_connect" and "sw_connect" not in sys.modules:
    sys.modules["sw_connect"] = sys.modules[__name__]

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

    from .path_security import (
        PROTECTED_FILENAMES_LOWER as _PROTECTED_FILENAMES_LOWER,
        get_final_path as _ps_get_final_path,
        has_forbidden_path_syntax as _has_forbidden_path_syntax,
        reject_forbidden_expand,
        require_allowed_path,
        safe_ensure_parent_dir,
        validate_path_against_allowed_roots,
        validate_nested_tool_paths,
    )

except ImportError:

    from path_security import (
        PROTECTED_FILENAMES_LOWER as _PROTECTED_FILENAMES_LOWER,
        get_final_path as _ps_get_final_path,
        has_forbidden_path_syntax as _has_forbidden_path_syntax,
        reject_forbidden_expand,
        require_allowed_path,
        safe_ensure_parent_dir,
        validate_path_against_allowed_roots,
        validate_nested_tool_paths,
    )



try:

    from .sw_preflight import ensure_solidworks_installed, import_com_dependencies

except ImportError:

    from sw_preflight import ensure_solidworks_installed, import_com_dependencies



pythoncom, win32com_client, VARIANT = import_com_dependencies()

try:

    from .sw_process import solidworks_processes, list_solidworks_instances, is_instance_responding, get_instance_window_title

    from .sw_job_object import init_orphan_guard, assign_process_to_job

except ImportError:

    from sw_process import solidworks_processes, list_solidworks_instances, is_instance_responding, get_instance_window_title

    try:

        from sw_job_object import init_orphan_guard, assign_process_to_job

    except ImportError:

        init_orphan_guard = lambda: None

        assign_process_to_job = lambda p: False





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



_SESSION_OWNED_DOCUMENTS = set()





def _canonical_doc_path(p: str) -> tuple[str, str]:
    abs_p = os.path.normcase(os.path.abspath(p))
    real_p = os.path.normcase(os.path.realpath(abs_p))
    return abs_p, real_p


def register_owned_document(doc_or_title_or_path):
    """Explicitly register a document as owned by this automation session.

    FIX RT-SEC-03 / BUG-010:
    - Saved documents (non-empty path) are keyed STRICTLY by canonical path
      (abspath + realpath), NEVER by bare GetTitle / basename / stem.
    - Unsaved documents (empty GetPathName) are keyed ONLY by exact full title
      (never extension-stripped stem).
    """
    if not doc_or_title_or_path:
        return

    if hasattr(doc_or_title_or_path, "GetTitle"):
        p = ""
        t = ""
        try:
            p = str(get_com_member(doc_or_title_or_path, "GetPathName") or "").strip()
        except Exception:
            p = ""
        try:
            t = str(get_com_member(doc_or_title_or_path, "GetTitle") or "").strip()
        except Exception:
            t = ""
        if p:
            abs_p, real_p = _canonical_doc_path(p)
            _SESSION_OWNED_DOCUMENTS.add(abs_p)
            _SESSION_OWNED_DOCUMENTS.add(real_p)
        elif t:
            _SESSION_OWNED_DOCUMENTS.add(t)
    elif isinstance(doc_or_title_or_path, str):
        s = doc_or_title_or_path.strip()
        if not s:
            return
        if os.path.isabs(s) or os.path.sep in s or "/" in s:
            abs_p, real_p = _canonical_doc_path(s)
            _SESSION_OWNED_DOCUMENTS.add(abs_p)
            _SESSION_OWNED_DOCUMENTS.add(real_p)
        else:
            _SESSION_OWNED_DOCUMENTS.add(s)


def is_document_owned(doc_or_title, path=None, allowed_roots=None) -> bool:
    """
    Check if a document is provably owned by this session and within allowed sandbox roots.
    Returns True only if confirmed; returns False for any arbitrary user files.
    """
    if doc_or_title is None and not path:
        return False

    title_str = ""
    path_str = str(path or "").strip()

    if hasattr(doc_or_title, "GetTitle"):
        try:
            title_str = str(get_com_member(doc_or_title, "GetTitle") or "").strip()
        except Exception:
            pass
        if not path_str:
            try:
                path_str = str(get_com_member(doc_or_title, "GetPathName") or "").strip()
            except Exception:
                pass
    elif isinstance(doc_or_title, str):
        raw = doc_or_title.strip()
        if os.path.isabs(raw) or (os.path.sep in raw) or ("/" in raw):
            if not path_str:
                path_str = raw
            title_str = os.path.basename(raw)
        else:
            title_str = raw

    # DEF-SEC-01 / DEF-SEC-02 / RT-SEC-03 强化：
    # 1. 有物理路径的文档必须严格按规范路径命中 _SESSION_OWNED_DOCUMENTS，禁止回退标题/文件名匹配。
    # 2. 仅无路径的未保存新建文档允许按完整精确标题匹配（禁止去扩展名匹配）。
    # 3. 凡具备物理路径者必须处于 DSH_ALLOWED_ROOTS 白名单目录内。
    is_registered = False
    if path_str:
        abs_p, real_p = _canonical_doc_path(path_str)
        is_registered = (abs_p in _SESSION_OWNED_DOCUMENTS) or (real_p in _SESSION_OWNED_DOCUMENTS)
    elif title_str:
        is_registered = title_str in _SESSION_OWNED_DOCUMENTS

    if not is_registered:
        return False

    if path_str and not validate_path_against_allowed_roots(path_str, allowed_roots):
        return False

    return True





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
    """Fail-closed 路径规范化：拒绝环境变量/%VAR%/~/非法语法并结合 DSH_DEFAULT_CWD 绝对化。"""
    return reject_forbidden_expand(file_path)


def _ensure_parent_dir(file_path):
    """先校验 DSH_ALLOWED_ROOTS 再安全创建父目录，并在创建后二次物理校验（防 TOCTOU）。"""
    return safe_ensure_parent_dir(file_path, label="output_path")





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

        self._lifecycle_lock = threading.RLock()



    def start(self):

        with self._lifecycle_lock:

            if self._running and self._thread and self._thread.is_alive():

                return

            self._running = True

            self._ready_event.clear()

            self._init_error = None

            self._thread = threading.Thread(

                target=self._worker_loop,

                name="DSH-SolidWorks-STAWorker",

                daemon=True,

            )

            self._thread.start()

            if not self._ready_event.wait(timeout=10.0):

                self._running = False

                raise RuntimeError("DesktopPinnedStaWorker startup timed out")

            if self._init_error:

                self._running = False

                raise RuntimeError(f"DesktopPinnedStaWorker startup failed: {self._init_error}")



    def restart(self, force: bool = False):

        """安全重启 STA 工作线程并重建纯净 COM 上下文。"""

        with self._lifecycle_lock:

            self._running = False

            try:

                self._queue.put_nowait(None)

            except Exception:

                pass

            if self._thread and self._thread.is_alive():

                self._thread.join(timeout=1.0)

            self._queue = queue.Queue()

            self.start()



    def is_healthy(self, timeout: float = 1.0) -> bool:

        """快速探活 STA 工作线程响应性。"""

        if not self._running or self._thread is None or not self._thread.is_alive():

            return False

        try:

            return bool(self.execute(lambda: True, timeout=timeout))

        except Exception:

            return False



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

        if not self._running or self._thread is None or not self._thread.is_alive():

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
    """解析物理路径（含 Windows Directory Junction / Symlink）。委托给 path_security.get_final_path。"""
    return _ps_get_final_path(target_path)





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





# _PROTECTED_FILENAMES_LOWER, _has_forbidden_path_syntax, validate_path_against_allowed_roots
# 已统一由 scripts.path_security 导出并在顶部重绑定（保持向后兼容导出名，fail-closed）。





def _get_active_object(prog_id):

    """

    获取活动 COM 对象，支持 Windows 跨桌面/沙箱穿透。

    通过常驻 DesktopPinnedStaWorker 在 Default 桌面与 STA 环境下稳定挂接。

    """

    worker = get_sta_worker()

    if threading.current_thread() == worker._thread:

        return win32com_client.GetActiveObject(prog_id)

    return worker.execute(lambda: win32com_client.GetActiveObject(prog_id))





def is_co_e_server_exec_failure(exc: Exception) -> bool:
    """检测异常是否为 CO_E_SERVER_EXEC_FAILURE (0x80080005，服务执行失败/超时)。"""
    if exc is None:
        return False
    if hasattr(exc, "hresult") and exc.hresult == -2146959355:
        return True
    if hasattr(exc, "args") and exc.args and isinstance(exc.args[0], int) and exc.args[0] == -2146959355:
        return True
    s = str(exc)
    return "0x80080005" in s or "80080005" in s or "CO_E_SERVER_EXEC_FAILURE" in s or "-2146959355" in s


def is_launch_allowed(allow_launch=None):
    """@brief 判断当前策略是否允许通过 COM Dispatch 拉起新 SolidWorks 进程（默认 fail-closed 禁止）。"""
    if allow_launch is not None:
        return bool(allow_launch)
    env_launch = os.environ.get("DSH_ALLOW_LAUNCH_SW", "0").strip().lower()
    env_mode = os.environ.get("DSH_POLICY_MODE", "").strip().lower()
    return (env_launch in {"1", "true", "yes"}) and (env_mode != "read-only")


def connect_solidworks(version=None, wait_seconds=5, visible=True, return_metadata=False, target_pid=None, allow_launch=None):

    """

    连接到 SolidWorks 实例。



    参数:

        version: SolidWorks 版本年份（如 2024），None 则自动检测

        wait_seconds: 启动新实例后等待秒数

        visible: 启动新实例后是否显示窗口

        return_metadata: 是否返回连接元数据字典

        target_pid: 指定连接的目标 SolidWorks 进程 PID（多实例支持）



    返回:

        (sw, model) 元组，model 可能为 None（无打开的文档时）

    """

    worker = get_sta_worker()

    if worker and threading.current_thread() != worker._thread:

        return worker.execute(lambda: connect_solidworks(version, wait_seconds, visible, return_metadata, target_pid, allow_launch))

    effective_allow_launch = is_launch_allowed(allow_launch)

    ensure_solidworks_installed()

    # 初始化防孤儿保护
    try:
        init_orphan_guard()
    except Exception:
        pass

    prog_id = _prog_id_for_version(version)

    sw = None

    launched_here = False

    dispatched = False

    # 启动和附着共享同一把互斥锁，避免多个 worker 同时拉起实例。

    with _LaunchGuard():

        before = solidworks_processes()

        requested_pid = None
        if target_pid is not None:
            if isinstance(target_pid, bool) or not isinstance(target_pid, int) or target_pid <= 0:
                raise SolidWorksConnectionError(
                    "SW_INVALID_TARGET_PID",
                    "connect",
                    f"非法目标 PID ({target_pid!r})，必须为正整数",
                )
            requested_pid = int(target_pid)

        # 多实例检测与提示
        instances = list_solidworks_instances()
        if len(instances) > 1 and target_pid is None:
            print(f"[提示] 检测到系统中运行着 {len(instances)} 个 SolidWorks 实例，默认连接主活动实例。可通过 target_pid 指定特定实例。")

        try:

            sw = _get_active_object(prog_id)

            if requested_pid is not None and sw is not None:
                actual_pid = int(get_com_member(sw, "GetProcessID") or 0)
                if actual_pid != requested_pid:
                    raise SolidWorksConnectionError(
                        "SW_TARGET_PID_MISMATCH",
                        "attach",
                        f"当前活动 COM 实例 PID ({actual_pid}) 与请求的目标 PID ({requested_pid}) 不一致，已拒绝绑定错误实例",
                    )

            print(f"已连接到运行中的 SolidWorks 实例（ProgID: {prog_id}）")

        except SolidWorksConnectionError:

            raise

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

                        if not effective_allow_launch:
                            raise SolidWorksConnectionError("SW_LAUNCH_PROHIBITED", "attach", "已有实例尚不可连接，且当前策略禁止自动 Dispatch 启动 SolidWorks")

                        try:

                            worker = get_sta_worker()

                            sw = worker.execute(lambda: win32com_client.Dispatch(prog_id))

                            dispatched = True

                        except Exception as disp_err:

                            if is_co_e_server_exec_failure(disp_err):
                                print(f"[诊断] 遭遇 CO_E_SERVER_EXEC_FAILURE (0x80080005)，等待已有进程进入就绪态并重试一次...")
                                time.sleep(1.5)
                                try:
                                    sw = _get_active_object(prog_id)
                                except Exception:
                                    pass

                            if sw is None:
                                raise SolidWorksConnectionError("SW_INSTANCE_NOT_READY", "attach", f"已有实例尚不可连接 ({disp_err})，已阻止重复启动")

                if sw is None:

                    if not effective_allow_launch:
                        raise SolidWorksConnectionError("SW_LAUNCH_PROHIBITED", "attach", "SolidWorks 未运行，且只读模式/只读工具调用禁止自动启动新进程")

                    try:
                        sw = win32com_client.Dispatch(prog_id)
                        dispatched = True
                    except Exception as first_disp_err:
                        if is_co_e_server_exec_failure(first_disp_err):
                            print(f"[诊断] Dispatch 启动抛出 CO_E_SERVER_EXEC_FAILURE (0x80080005)，尝试等待 2 秒并自动恢复重试...")
                            time.sleep(2.0)
                            sw = win32com_client.Dispatch(prog_id)
                            dispatched = True
                        else:
                            raise

                    try:

                        pid = int(get_com_member(sw, "GetProcessID"))

                        launched_here = before is not None and pid > 0 and pid not in before
                        # 安全准则：SolidWorks 桌面主进程绝不纳入 KILL_ON_JOB_CLOSE 的 Job Object，避免插件退出或崩溃时误杀用户 CAD 实例
                        if launched_here:
                            pass

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

        if requested_pid is not None:
            actual_pid = int(get_com_member(sw, "GetProcessID") or 0)
            if actual_pid != requested_pid:
                close_owned_solidworks(sw, launched_here)
                raise SolidWorksConnectionError(
                    "SW_TARGET_PID_MISMATCH",
                    "verify",
                    f"目标 PID ({requested_pid}) 与实际连接实例 PID ({actual_pid}) 不一致，已拒绝连接",
                )

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



    proc_id = get_com_member(sw, "GetProcessID", default=None)
    proc_create_time = _get_process_create_time(proc_id)
    _LAST_CONNECTED_INSTANCE["pid"] = proc_id
    _LAST_CONNECTED_INSTANCE["create_time"] = proc_create_time

    metadata = {

        "prog_id": prog_id,

        "requested_version": int(version) if version is not None else None,

        "started_by_cad_studio": launched_here,

        "actual_version": actual["year"],

        "actual_revision": actual["revision"],

        "process_id": proc_id,

        "process_create_time": proc_create_time,

    }

    return (sw, model, metadata) if return_metadata else (sw, model)


_LAST_CONNECTED_INSTANCE = {"pid": None, "create_time": None}


def _get_process_create_time(pid):
    """获取仍在运行中的进程创建时间戳（100ns FILETIME 转换秒），用于区分 PID 复用与已退出进程。"""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_t = wintypes.FILETIME()
            kernel_t = wintypes.FILETIME()
            user_t = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_t),
                ctypes.byref(kernel_t),
                ctypes.byref(user_t),
            ):
                return None
            ft_exit = (exit_t.dwHighDateTime << 32) | exit_t.dwLowDateTime
            if ft_exit != 0:
                return None
            ft = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            if ft <= 0:
                return None
            return round((ft - 116444736000000000) / 10_000_000.0, 6)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def get_connected_instance_identity():
    """返回最近一次连接的 SolidWorks 进程 (pid, create_time) 身份快照，并校验当前进程是否存活或发生重启替换。"""
    pid = _LAST_CONNECTED_INSTANCE.get("pid")
    recorded_ct = _LAST_CONNECTED_INSTANCE.get("create_time")
    live_ct = _get_process_create_time(pid) if pid else None
    alive = bool(pid and live_ct is not None)
    replaced = bool(pid and recorded_ct is not None and live_ct is not None and abs(live_ct - recorded_ct) > 1e-3)
    identity_valid = bool(pid and recorded_ct is not None and live_ct is not None and not replaced)
    return {
        "pid": pid,
        "create_time": recorded_ct,
        "live_create_time": live_ct,
        "alive": alive,
        "instance_replaced": replaced,
        "identity_valid": identity_valid,
    }


def verify_connected_instance_identity(expected_pid=None, expected_create_time=None):
    """Fail-closed 校验目标进程 (pid, create_time) 是否仍为同一存活实例。"""
    snap = get_connected_instance_identity()
    pid = snap["pid"] if expected_pid is None else expected_pid
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return {"ok": False, "reason": "INVALID_PID", **snap}
    if expected_pid is not None and snap["pid"] is not None and snap["pid"] != expected_pid:
        return {"ok": False, "reason": "PID_MISMATCH", **snap}
    rec_ct = snap["create_time"] if expected_create_time is None else expected_create_time
    if rec_ct is None:
        return {"ok": False, "reason": "RECORDED_CREATE_TIME_UNAVAILABLE", **snap}
    live_ct = _get_process_create_time(pid)
    if live_ct is None:
        return {"ok": False, "reason": "PROCESS_EXITED_OR_UNREADABLE", **snap, "live_create_time": None, "alive": False}
    if abs(live_ct - rec_ct) > 1e-3:
        return {"ok": False, "reason": "PID_REUSED_OR_REPLACED", **snap, "live_create_time": live_ct, "instance_replaced": True, "identity_valid": False}
    return {"ok": True, "reason": "OK", "pid": pid, "create_time": rec_ct, "live_create_time": live_ct, "alive": True, "instance_replaced": False, "identity_valid": True}





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

        template_path = require_allowed_path(template_path, label="template_path")



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

    register_owned_document(model)

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

        # FIX BUG-001 / RT-SEC-01：仅非只读打开才登记可写所有权，避免只读引用打开提升写权限。
        if not read_only:
            register_owned_document(existing_model)
            register_owned_document(file_path)

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

        if not read_only:
            register_owned_document(model)
            register_owned_document(file_path)

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



    existing_path = str(get_com_member(model, "GetPathName") or "").strip()
    if existing_path:
        if not is_document_owned(model, path=existing_path):
            raise PermissionError("DEF-SEC-01: Existing document is not owned by current session. Refusing save.")
    else:
        if not is_document_owned(model):
            # FIX BUG-016：旧实现用子串包含（owned in curr_title）判定“派生自有”，
            # 使标题包含任一已登记键的文档被自动授权。授权必须来自显式登记/新建，
            # 因此这里直接拒绝，不再做启发式放行。
            raise PermissionError("DEF-SEC-01: Document is not owned by current automation session.")



    target_path = _expand_path(target_path)

    if not validate_path_against_allowed_roots(target_path):

        raise PermissionError(f"Access denied: target path '{target_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")



    safe_ensure_parent_dir(target_path, label="save_path")

    save_code = get_com_member(model, "SaveAs3", target_path, 0, 1)

    success = (save_code == 0)



    if success:

        print(f"保存成功: {target_path}")

        if not existing_path:
            try:
                old_t = str(get_com_member(model, "GetTitle") or "").strip()
                if old_t and old_t in _SESSION_OWNED_DOCUMENTS:
                    _SESSION_OWNED_DOCUMENTS.discard(old_t)
            except Exception:
                pass

        register_owned_document(model)

        register_owned_document(target_path)

    else:

        print(f"保存失败, SaveAs3 错误码: {save_code}")

    return bool(success)





def close_document(sw, doc_or_title, force_discard=False, allowed_roots=None, save_before_close=False) -> bool:

    """

    安全关闭指定 SolidWorks 文档。

    

    三层防御安全边界：

    1. 校验目标非空，禁止空参数导致误关当前活动文档；

    2. 严格核验证档所有权（必须属于本会话创建或处于沙箱允许目录），绝不关闭外部/用户文档；

    3. 核验未保存状态（GetSaveFlag），若有未保存修改且未显式指定 force_discard=True，拒绝关闭；

    4. 坚决禁止调用 CloseAllDocuments。

    """

    if doc_or_title is None:

        return False



    target_doc = None

    target_title = ""

    target_path = ""



    if hasattr(doc_or_title, "GetTitle"):

        target_doc = doc_or_title

        try:

            target_title = str(get_com_member(target_doc, "GetTitle") or "").strip()

            target_path = str(get_com_member(target_doc, "GetPathName") or "").strip()

        except Exception:

            pass

    elif isinstance(doc_or_title, str):

        target_title = doc_or_title.strip()

        if os.path.isabs(target_title):

            target_path = target_title

            target_title = os.path.basename(target_title)



    if not target_title and not target_path:

        return False



    # 若尚未获取目标文档对象，尝试从 sw.GetDocuments() 中按规范路径优先，其次严格完整标题匹配（禁止扩展名前缀撞库）

    if target_doc is None and sw is not None:

        try:

            docs = get_com_member(sw, "GetDocuments") or []

            norm_target_path = _canonical_doc_path(target_path)[0] if target_path else None
            path_matches = []
            title_matches = []
            for d in docs:
                dt = str(get_com_member(d, "GetTitle") or "").strip()
                dp = str(get_com_member(d, "GetPathName") or "").strip()
                if norm_target_path and dp and _canonical_doc_path(dp)[0] == norm_target_path:
                    path_matches.append((d, dt, dp))
                elif not norm_target_path and target_title and dt and dt.lower() == target_title.strip().lower():
                    title_matches.append((d, dt, dp))

            if path_matches:
                target_doc, dt, dp = path_matches[0]
            elif len(title_matches) > 1:
                raise ValueError(f"存在多个同名文档 '{target_title}'，请改用 document_path 精确指定要关闭的文档")
            elif len(title_matches) == 1:
                target_doc, dt, dp = title_matches[0]
            else:
                dt, dp = "", ""

            if target_doc is not None:
                if not target_title:
                    target_title = dt
                if not target_path:
                    target_path = dp

        except ValueError:
            raise
        except Exception:

            pass



    # 第二层防线：所有权与沙箱核验

    owned = is_document_owned(target_doc or target_title, target_path, allowed_roots)

    if not owned:

        raise PermissionError(

            f"安全边界拦截: 文档 '{target_title or target_path}' 未由当前自动化任务创建，且不在允许的沙箱目录内，严禁关闭用户或外部文档！"

        )

    if save_before_close:
        if target_doc is None:
            raise FileNotFoundError(f"无法在保存前定位已打开文档: {target_title or target_path}")
        if not target_path and not allowed_roots and not parse_allowed_roots_env():
            raise PermissionError("Access denied: DSH_ALLOWED_ROOTS is required before saving an unnamed document")
        saved = save_document(target_doc)
        if not saved:
            raise RuntimeError(f"Failed to save document before closing: {target_title or target_path}")

    # 第三层防线：未保存修改核验

    if target_doc is not None:

        try:

            is_dirty = bool(get_com_member(target_doc, "GetSaveFlag"))

            if is_dirty and not force_discard:

                raise ValueError(

                    # FIX BUG-003：MCP 的 close_documents 未暴露该参数，旧文案却让用户传它，
                    # 形成“无法关闭”的死路。文案改为可执行的真实指引。
                    f"安全拦截: 文档 '{target_title}' 包含未保存的修改。请先保存后再关闭；"
                    f"本接口不提供丢弃未保存修改的选项。"

                )

        except Exception as e:

            if isinstance(e, (PermissionError, ValueError)):

                raise



    # 执行精准关闭

    try:

        title_to_close = target_title or (os.path.basename(target_path) if target_path else "")

        if not title_to_close:

            return False

        get_com_member(sw, "CloseDoc", title_to_close)

        # 从会话登记集中注销

        if title_to_close in _SESSION_OWNED_DOCUMENTS:

            _SESSION_OWNED_DOCUMENTS.discard(title_to_close)

        if target_path and target_path in _SESSION_OWNED_DOCUMENTS:

            _SESSION_OWNED_DOCUMENTS.discard(target_path)

        return True

    except Exception as exc:

        if isinstance(exc, (PermissionError, ValueError)):

            raise

        return False





def close_all_documents(sw, *args, **kwargs):

    """

    [永久封禁] 全局无差别关闭文档接口。

    根据 DEF-SEC-01 最高安全约束，禁止使用 CloseAllDocuments。

    """

    raise PermissionError("CloseAllDocuments is permanently forbidden by security policy DEF-SEC-01 to protect user workspace integrity.")





def mm(value):

    """毫米转米（SolidWorks API 单位）。"""

    return value / 1000.0





def deg(value):

    """角度转弧度。"""

    import math

    return value * math.pi / 180.0

