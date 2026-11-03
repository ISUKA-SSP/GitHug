"""Launch VS Code with a folder, without executing a shell command."""
import os
from pathlib import Path
import shutil
import subprocess


def find_vscode():
    candidates = []
    for variable, suffix in (('LOCALAPPDATA', ('Programs', 'Microsoft VS Code', 'Code.exe')),
                             ('ProgramFiles', ('Microsoft VS Code', 'Code.exe')),
                             ('ProgramFiles(x86)', ('Microsoft VS Code', 'Code.exe'))):
        root = os.environ.get(variable)
        if root: candidates.append(Path(root).joinpath(*suffix))
    for path in candidates:
        if path.is_file(): return str(path)
    found = shutil.which('code') or shutil.which('code.exe')
    if found:
        path = Path(found)
        # Windows' code.cmd is a launcher. Prefer its real executable, not cmd.exe.
        if path.suffix.casefold() in ('.cmd', '.bat'):
            executable = path.parent.parent / 'Code.exe'
            if executable.is_file(): return str(executable)
        else: return str(path)
    return None


def open_vscode(folder, executable=None):
    directory = Path(folder).resolve(strict=True)
    if not directory.is_dir(): raise ValueError('開くフォルダーが見つかりません。')
    executable = executable or find_vscode()
    if not executable: raise FileNotFoundError('VS Codeが見つかりません。「Code.exe」を選ぶか、VS Codeをインストールしてください。')
    return subprocess.Popen([str(executable), '--new-window', str(directory)], cwd=directory)
