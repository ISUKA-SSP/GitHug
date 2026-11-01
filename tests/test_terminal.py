import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from githug.terminal import powershell_arguments, open_powershell

class TerminalTests(unittest.TestCase):
    def test_multiline_and_special_folder_names_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "日本語 [test] ' $value"
            folder.mkdir()
            commands = '$env:EXAMPLE = "a b"\nWrite-Output "日本語"\npython -m app'
            args, cwd = powershell_arguments(folder, commands)
            script = base64.b64decode(args[-1]).decode('utf-16-le')
            self.assertEqual(cwd, folder.resolve())
            self.assertIn('-NoExit', args)
            self.assertIn("Set-Location -LiteralPath '" + str(folder.resolve()).replace("'", "''") + "' -ErrorAction Stop\n", script)
            self.assertTrue(script.endswith(commands))

    def test_blank_command_and_invalid_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _ = powershell_arguments(directory)
            self.assertTrue(base64.b64decode(args[-1]).decode('utf-16-le').endswith('\n'))
            with self.assertRaises(ValueError): powershell_arguments(directory, 'a' * 20000)
            file = Path(directory) / 'file'
            file.touch()
            with self.assertRaises(ValueError): powershell_arguments(file)
        with self.assertRaises(FileNotFoundError): powershell_arguments(directory)

    def test_launch_creates_console_with_selected_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            # Keep Windows platform mocking scoped to the module's guard, not pathlib internals.
            with patch('githug.terminal.powershell_arguments', return_value=(['powershell.exe', '-NoExit'], directory)), \
                 patch('githug.terminal.os') as os_mock, \
                 patch('githug.terminal.subprocess.Popen') as launch, \
                 patch('githug.terminal.subprocess.CREATE_NEW_CONSOLE', 16, create=True):
                os_mock.name = 'nt'
                open_powershell(directory, 'Get-Location')
                launch.assert_called_once_with(['powershell.exe', '-NoExit'], cwd=directory, creationflags=16)
