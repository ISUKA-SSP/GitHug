"""Windows Shell recycle operation. Never fall back to unlink/rmtree."""
import ctypes
import os
from pathlib import Path

class RecycleError(RuntimeError):
    pass


def recycle_folder(folder):
    if os.name!='nt':raise RecycleError('ごみ箱への移動はWindowsで利用できます。')
    import pythoncom
    import pywintypes
    from win32com.shell import shell, shellcon
    from win32com.server.policy import DesignatedWrapPolicy
    from win32com.server.exception import COMException
    path=Path(folder).resolve(strict=True)
    # Network/removable storage has no dependable local recycle bin.
    drive_type=ctypes.windll.kernel32.GetDriveTypeW
    drive_type.argtypes=[ctypes.c_wchar_p];drive_type.restype=ctypes.c_uint
    if drive_type(path.anchor)!=3:raise RecycleError('この保存場所ではごみ箱への移動を利用できません。エクスプローラーで確認してください。')
    methods=('StartOperations','FinishOperations','PreRenameItem','PostRenameItem','PreMoveItem','PostMoveItem',
             'PreCopyItem','PostCopyItem','PreDeleteItem','PostDeleteItem','PreNewItem','PostNewItem',
             'UpdateProgress','ResetTimer','PauseTimer','ResumeTimer')
    class Sink(DesignatedWrapPolicy):
        _com_interfaces_=[shell.IID_IFileOperationProgressSink]
        _public_methods_=list(methods)
        def __init__(self):
            self._wrap_(self);self.recycled=False;self.refused=False;self.destination=None
        def PreDeleteItem(self,flags,item):
            if not flags & 0x80: # TSF_DELETE_RECYCLE_IF_POSSIBLE
                self.refused=True
                raise COMException(desc='Permanent deletion is not allowed.',scode=-2147467260)
        def PostDeleteItem(self,flags,item,result,new_item):
            if not result & 0x80000000 and new_item is not None:
                self.recycled=True
                try:self.destination=new_item.GetDisplayName(0x80058000) # SIGDN_FILESYSPATH
                except pywintypes.com_error:pass
    def noop(self,*args):pass
    for name in methods:
        if name not in ('PreDeleteItem','PostDeleteItem'):setattr(Sink,name,noop)
    pythoncom.CoInitialize()
    try:
        operation=pythoncom.CoCreateInstance(shell.CLSID_FileOperation,None,pythoncom.CLSCTX_ALL,shell.IID_IFileOperation)
        # Recycle, record undo, fail early, and suppress error dialogs. No permanent-delete fallback.
        operation.SetOperationFlags(0x20000000|0x00080000|0x00100000|shellcon.FOF_NOERRORUI|shellcon.FOF_SILENT|shellcon.FOF_NOCONFIRMATION)
        sink=Sink();wrapped=pythoncom.WrapObject(sink,shell.IID_IFileOperationProgressSink)
        item=shell.SHCreateItemFromParsingName(str(path),None,shell.IID_IShellItem)
        operation.DeleteItem(item,wrapped)
        result=operation.PerformOperations()
        if result or operation.GetAnyOperationsAborted() or sink.refused or not sink.recycled:
            raise RecycleError('ごみ箱への移動を完了できませんでした。保存場所や使用中のアプリを確認してください。')
        if path.exists():raise RecycleError('フォルダーが残っています。一覧を再表示して確認してください。')
        return sink.destination
    except pywintypes.com_error as exc:
        raise RecycleError('ごみ箱への移動を完了できませんでした。使用中のアプリや保存場所を確認してください。\n'+str(exc.strerror)) from None
    finally:pythoncom.CoUninitialize()
