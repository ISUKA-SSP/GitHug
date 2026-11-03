# Bundled components

GitHug's portable package contains the original application, a Python runtime, Tcl/Tk,
the PyInstaller bootloader, and the upstream MinGit distribution when enabled.

- Python: https://www.python.org/ — license text is copied into `licenses`.
- Tcl/Tk: https://www.tcl.tk/ — available license terms are copied into `licenses`.
- PyInstaller: https://pyinstaller.org/ — GPL with the PyInstaller bootloader exception;
  its available license text is copied into `licenses`.
- MinGit / Git for Windows: https://gitforwindows.org/mingit.html — upstream files and
  their notices are preserved under `tools/git`.
  Pinned binary release: https://github.com/git-for-windows/git/releases/tag/v2.56.0.windows.4
  Git source for the corresponding tag: https://github.com/git-for-windows/git/tree/v2.56.0.windows.4
  Build/distribution scripts and component sources: https://github.com/git-for-windows/build-extra

The complete MinGit archive is extracted without removing its component files or notices.
Exact package versions and the downloaded archive's SHA-256 are recorded in `build-info.json`.
