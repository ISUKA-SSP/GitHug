"""Windows job ownership: closing GitHug also closes its console process tree."""
import ctypes
import threading
from ctypes import wintypes

class _Basic(ctypes.Structure):
    _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),
              ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),
              ('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),
              ('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
class _IO(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
class _Extended(ctypes.Structure):
    _fields_=[('BasicLimitInformation',_Basic),('IoInfo',_IO),('ProcessMemoryLimit',ctypes.c_size_t),
              ('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]

class ProcessJob:
    def __init__(self,pid):
        self._lock=threading.Lock()
        api=ctypes.WinDLL('kernel32',use_last_error=True);self.api=api;self.handle=None
        api.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];api.CreateJobObjectW.restype=wintypes.HANDLE
        api.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];api.SetInformationJobObject.restype=wintypes.BOOL
        api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
        api.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];api.AssignProcessToJobObject.restype=wintypes.BOOL
        api.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT];api.TerminateJobObject.restype=wintypes.BOOL
        api.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];api.TerminateProcess.restype=wintypes.BOOL
        api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
        job=api.CreateJobObjectW(None,None)
        if not job:raise ctypes.WinError(ctypes.get_last_error())
        process=None
        try:
            limits=_Extended();limits.BasicLimitInformation.LimitFlags=0x2000 # KILL_ON_JOB_CLOSE
            if not api.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)):raise ctypes.WinError(ctypes.get_last_error())
            process=api.OpenProcess(0x0100|0x0001,False,pid) # SET_QUOTA | TERMINATE
            if not process:raise ctypes.WinError(ctypes.get_last_error())
            if not api.AssignProcessToJobObject(job,process):raise ctypes.WinError(ctypes.get_last_error())
            self.handle=job
        except Exception:
            # The shell has not received user commands yet. Never leave an unowned shell.
            if process:api.TerminateProcess(process,1)
            api.CloseHandle(job)
            raise
        finally:
            if process:api.CloseHandle(process)

    def terminate(self):
        with self._lock:
            if self.handle and not self.api.TerminateJobObject(self.handle,1):
                raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        with self._lock:
            if self.handle:self.api.CloseHandle(self.handle);self.handle=None
