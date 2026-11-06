import os
import unittest

from githug.core import git


@unittest.skipUnless(os.name == 'nt', 'Windows standard handles')
class GitStdinTests(unittest.TestCase):
    def test_git_can_start_when_gui_stdin_handle_is_invalid(self):
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
        kernel.SetStdHandle.restype = wintypes.BOOL

        stdin_slot = wintypes.DWORD(-10)
        original = kernel.GetStdHandle(stdin_slot)
        self.assertTrue(kernel.SetStdHandle(stdin_slot, 0x7FFFFFFD))
        try:
            self.assertTrue(git('--version').startswith('git version '))
            digest = git('hash-object', '--stdin', input_text='hello\n')
            self.assertEqual(digest.strip(), 'ce013625030ba8dba906f756967f9e9ca394464a')
        finally:
            self.assertTrue(kernel.SetStdHandle(stdin_slot, original))
