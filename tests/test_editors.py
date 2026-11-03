import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from githug.editors import find_vscode, open_vscode

class EditorTests(unittest.TestCase):
    def test_folder_is_passed_as_one_argument_without_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "日本語 & $test ' folder"
            folder.mkdir()
            with patch('githug.editors.subprocess.Popen') as launch:
                open_vscode(folder, 'Code.exe')
                launch.assert_called_once_with(['Code.exe','--new-window',str(folder.resolve())],cwd=folder.resolve())

    def test_standard_install_and_cmd_launcher_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary)/'Programs'/'Microsoft VS Code'/'Code.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict(os.environ, {'LOCALAPPDATA':temporary}, clear=True):
                self.assertEqual(find_vscode(),str(executable))
            launcher = executable.parent/'bin'/'code.cmd'
            launcher.parent.mkdir(); launcher.touch()
            with patch.dict(os.environ, {}, clear=True), patch('githug.editors.shutil.which',return_value=str(launcher)):
                self.assertEqual(find_vscode(),str(executable))

    def test_missing_editor_does_not_start_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('githug.editors.find_vscode',return_value=None), patch('githug.editors.subprocess.Popen') as launch:
                with self.assertRaises(FileNotFoundError): open_vscode(temporary)
                launch.assert_not_called()
