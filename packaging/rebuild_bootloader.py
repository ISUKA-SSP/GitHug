"""Build the official, hash-verified PyInstaller bootloader with standard options."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
VERSION = '6.22.3'
URL = 'https://files.pythonhosted.org/packages/63/41/f90302845945abd4ed647933ff5ee7c6ac93983187be67f897b6cb613331/pyinstaller-6.22.3.tar.gz'
SHA256 = '05eb2f5615503e72939a7224d68b4aff572c6b0438ee4a17d0a4b481f399362d'

def main():
    if os.name != 'nt':
        raise SystemExit('Windows build only')
    target = ROOT / 'build' / 'bootloader-source'
    target.mkdir(parents=True, exist_ok=True)
    archive = target / ('pyinstaller-' + VERSION + '.tar.gz')
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError('Official PyInstaller source hash mismatch')
    archive.write_bytes(data)
    env = dict(os.environ, PYINSTALLER_COMPILE_BOOTLOADER='1')
    subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', 'pyinstaller'], check=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--verbose', '--no-cache-dir',
                    '--no-deps', str(archive)], env=env, check=True)
    import PyInstaller
    bootloader = Path(PyInstaller.__file__).parent / 'bootloader' / 'Windows-64bit-intel' / 'runw.exe'
    info = {'version': VERSION, 'source_url': URL, 'source_sha256': SHA256,
            'compile_bootloader': True, 'options': 'standard configure all',
            'runw_sha256': hashlib.sha256(bootloader.read_bytes()).hexdigest()}
    (ROOT / 'build' / 'bootloader-build.json').write_text(json.dumps(info, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
