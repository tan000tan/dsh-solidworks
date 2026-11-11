"""@brief Windows Job Object 辅助模块，提供防孤儿进程守护机制。"""
import ctypes
from ctypes import wintypes
import os

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryLimit", ctypes.c_size_t),
        ("PeakJobMemoryLimit", ctypes.c_size_t),
    ]

_GLOBAL_JOB_HANDLE = None

def init_orphan_guard():
    """初始化当前进程的 Job Object 守护，所有在此之后被分配的子进程将在主进程退出时自动销毁。"""
    global _GLOBAL_JOB_HANDLE
    if os.name != "nt":
        return None
    
    if _GLOBAL_JOB_HANDLE is not None:
        return _GLOBAL_JOB_HANDLE

    kernel32 = ctypes.windll.kernel32
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

    success = kernel32.SetInformationJobObject(
        job,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info)
    )

    if not success:
        kernel32.CloseHandle(job)
        return None

    # Assign current process to job object
    current_process = kernel32.GetCurrentProcess()
    kernel32.AssignProcessToJobObject(job, current_process)
    _GLOBAL_JOB_HANDLE = job
    return job

PROTECTED_HOST_PROCESS_NAMES = {"sldworks.exe", "autocad.exe", "inventor.exe"}

def _get_process_image_name(handle):
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buf))
    if hasattr(kernel32, "QueryFullProcessImageNameW") and kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        return os.path.basename(buf.value).lower()
    return ""

def assign_process_to_job(process_handle_or_pid):
    """将指定的辅助进程句柄或 PID 绑定到 Job Object（严格禁止绑定任何 CAD 宿主主进程）。"""
    if os.name != "nt":
        return False
    job = init_orphan_guard()
    if not job:
        return False
    
    kernel32 = ctypes.windll.kernel32
    if isinstance(process_handle_or_pid, int):
        handle = kernel32.OpenProcess(0x1F0FFF, False, process_handle_or_pid)
        if not handle:
            return False
        try:
            pname = _get_process_image_name(handle)
            if pname in PROTECTED_HOST_PROCESS_NAMES:
                # 触发核心安全拦截：绝对禁止将宿主 CAD 主进程纳入 Job Object！
                return False
            return bool(kernel32.AssignProcessToJobObject(job, handle))
        finally:
            kernel32.CloseHandle(handle)
    else:
        pname = _get_process_image_name(process_handle_or_pid)
        if pname in PROTECTED_HOST_PROCESS_NAMES:
            return False
        return bool(kernel32.AssignProcessToJobObject(job, process_handle_or_pid))
