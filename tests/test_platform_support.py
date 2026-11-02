import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from githug.branding import logo_png, icon_bytes
from githug.platform_support import git_executable

class PackagingTests(unittest.TestCase):
    def test_png_and_multisize_icon_are_valid(self):
        png=logo_png(32)
        self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II',png[16:24]),(32,32))
        ico=icon_bytes()
        self.assertEqual(struct.unpack('<HHH',ico[:6]),(0,1,6))
        for index in range(6):
            entry=struct.unpack('<BBBBHHII',ico[6+16*index:22+16*index])
            size,offset=entry[-2:]
            self.assertEqual(ico[offset:offset+8],png[:8])
            self.assertLessEqual(offset+size,len(ico))

    def test_installed_git_wins_and_bundle_is_fallback(self):
        with patch.dict(os.environ,{'GITHUG_PREFER_BUNDLED_GIT':''}), patch('githug.platform_support.bundled_git',return_value='bundled.exe'), patch('githug.platform_support.shutil.which',return_value='installed.exe') as which:
            self.assertEqual(git_executable(),'installed.exe')
            which.return_value=None
            self.assertEqual(git_executable(),'bundled.exe')
        with patch.dict(os.environ,{'GITHUG_PREFER_BUNDLED_GIT':'1'}), patch('githug.platform_support.bundled_git',return_value='bundled.exe'):
            self.assertEqual(git_executable(),'bundled.exe')
