"""Open an independent Windows PowerShell session in a selected folder."""
import base64
import os
from pathlib import Path
import subprocess


def powershell_arguments(folder, commands=''):
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('作業場所にはフォルダーを選んでください。')
    # Encode the complete script, rather than interpolating user input into a shell command.
    # LiteralPath also handles brackets; single quotes in folder names must be doubled.
    literal = str(folder).replace("'", "''")
    script = "Set-Location -LiteralPath '" + literal + "' -ErrorAction Stop\n"
    script += commands.replace('\r\n', '\n')
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    if len(encoded) > 28000:
        raise ValueError('コマンドが長すぎます。処理を分けて実行してください。')
    executable = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' /
                     'WindowsPowerShell' / 'v1.0' / 'powershell.exe')
    return [executable, '-NoExit', '-EncodedCommand', encoded], folder


def open_powershell(folder, commands=''):
    if os.name != 'nt':
        raise RuntimeError('この機能はWindowsで利用できます。')
    arguments, directory = powershell_arguments(folder, commands)
    return subprocess.Popen(arguments, cwd=directory,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)
