"""Executable location and Windows window appearance, isolated from UI logic."""
import os
from pathlib import Path
import shutil
import sys


def app_directory():
    return Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent


def bundled_git():
    root=app_directory()/'tools'/'git'
    for relative in ('cmd/git.exe','bin/git.exe','ucrt64/bin/git.exe','mingw64/bin/git.exe'):
        candidate=root/relative
        if candidate.is_file():return str(candidate)
    return None


def git_executable():
    # Preserve existing credential helpers and user configuration when Git is installed.
    if os.environ.get('GITHUG_PREFER_BUNDLED_GIT')=='1':
        packaged=bundled_git()
        if packaged:return packaged
    found=shutil.which('git')
    if found:return found
    packaged=bundled_git()
    if packaged:return packaged
    for variable in ('ProgramFiles','LOCALAPPDATA'):
        root=os.environ.get(variable)
        if root:
            candidate=Path(root)/('Git/cmd/git.exe' if variable=='ProgramFiles' else 'Programs/Git/cmd/git.exe')
            if candidate.is_file():return str(candidate)
    return 'git'  # The caller provides the friendly missing-Git message.


def enable_dpi_awareness():
    if os.name!='nt':return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):pass


def dark_titlebar(window):
    if os.name!='nt':return
    try:
        import ctypes
        from ctypes import wintypes
        user32=ctypes.windll.user32
        user32.GetParent.argtypes=[wintypes.HWND]
        user32.GetParent.restype=wintypes.HWND
        handle=user32.GetParent(window.winfo_id()) or window.winfo_id()
        function=ctypes.windll.dwmapi.DwmSetWindowAttribute
        function.argtypes=[wintypes.HWND,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint]
        function.restype=ctypes.c_long
        value=ctypes.c_int(1)
        function(handle,20,ctypes.byref(value),ctypes.sizeof(value))
    except (AttributeError,OSError):pass
