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

## Embedded PowerShell panel

- pywinpty 3.1.2 (MIT): https://github.com/andfoy/pywinpty/tree/v3.1.2
  Windows ConPTY interface; includes Rust components from winpty-rs and PyO3.
  Distributed wheel notices are copied into `licenses/pywinpty`.
- pyte 0.8.2 (LGPLv3): https://github.com/selectel/pyte/tree/0.8.2
  The unmodified library source is included in `_internal/pyte` as separate,
  replaceable Python files, outside the frozen application archive. You may replace
  those files with a compatible modified version; modifying/reverse engineering
  GitHug for debugging modifications to this library is permitted.
  The license text is included in `licenses/pyte`. Application build scripts and
  source are available at https://github.com/ISUKA-SSP/GitHug .
- wcwidth 0.2.13 (MIT): https://github.com/jquast/wcwidth/tree/0.2.13
  Its available license is included in `licenses/wcwidth`.
