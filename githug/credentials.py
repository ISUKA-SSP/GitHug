"""Gemini key in the current Windows user's Credential Manager, never JSON.

Native API layout: Microsoft Learn, wincred/CREDENTIALW and CredReadW/CredWriteW.
"""
import ctypes
from ctypes import wintypes
import os

TARGET = 'GitHug/Gemini/APIKey'

class CredentialError(Exception):
    pass

class _Credential(ctypes.Structure):
    _fields_ = [('Flags',wintypes.DWORD),('Type',wintypes.DWORD),
                ('TargetName',wintypes.LPWSTR),('Comment',wintypes.LPWSTR),
                ('LastWritten',wintypes.FILETIME),('CredentialBlobSize',wintypes.DWORD),
                ('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',wintypes.DWORD),
                ('AttributeCount',wintypes.DWORD),('Attributes',ctypes.c_void_p),
                ('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]

class CredentialStore:
    def __init__(self,target=TARGET):
        self.target=target
        self.available=os.name=='nt'

    def _api(self):
        if not self.available:raise CredentialError('APIキーの保存はWindowsで利用できます。')
        api=ctypes.WinDLL('Advapi32.dll',use_last_error=True)
        api.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(_Credential))]
        api.CredReadW.restype=wintypes.BOOL
        api.CredWriteW.argtypes=[ctypes.POINTER(_Credential),wintypes.DWORD];api.CredWriteW.restype=wintypes.BOOL
        api.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD];api.CredDeleteW.restype=wintypes.BOOL
        api.CredFree.argtypes=[ctypes.c_void_p];api.CredFree.restype=None
        return api

    @staticmethod
    def _error(action):
        # Do not include the credential, API input or native exception text.
        return CredentialError(f'WindowsにAPIキーを{action}できませんでした（エラー番号 {ctypes.get_last_error()}）。')

    def read(self):
        if not self.available:return ''
        api=self._api();pointer=ctypes.POINTER(_Credential)()
        if not api.CredReadW(self.target,1,0,ctypes.byref(pointer)):
            if ctypes.get_last_error()==1168:return ''
            raise self._error('読み込み')
        try:return ctypes.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize).decode('utf-8')
        except UnicodeError:raise CredentialError('保存済みAPIキーを読み取れません。接続設定で保存し直してください。') from None
        finally:api.CredFree(pointer)

    def write(self,key):
        data=key.encode('utf-8')
        if not data or len(data)>2560:raise CredentialError('保存するAPIキーの長さを確認してください。')
        api=self._api();buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
        item=_Credential();item.Type=1;item.TargetName=self.target;item.UserName='Gemini'
        item.CredentialBlobSize=len(data);item.CredentialBlob=buffer;item.Persist=2
        if not api.CredWriteW(ctypes.byref(item),0):raise self._error('保存')

    def delete(self):
        if not self.available:return
        api=self._api()
        if not api.CredDeleteW(self.target,1,0) and ctypes.get_last_error()!=1168:raise self._error('削除')
