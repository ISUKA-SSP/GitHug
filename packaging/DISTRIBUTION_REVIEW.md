# Distribution review: 1.1.0a6

Chrome's dangerous-download warning is distinct from its uncommon-download warning. A clean Defender result cannot establish the reason for Chrome's decision or guarantee acceptance.

## Observed comparison

- The user explicitly confirmed downloading and launching 0.6.1 successfully.
- Between 1.1.0a4 and the blocked 1.1.0a5, no bundled native executable/DLL/PYD changed except GitHug.exe. Three mascot assets were added; Python cache and archive changes also occurred. This does not establish that images caused the warning.
- Both 0.6.1 and 1.1.0a5 used Python 3.13.17 and PyInstaller 6.22.3. Their bootloader code sections were identical, and both were unsigned with no Windows product version resource. Control Flow Guard was already enabled.

## Changes in this preview

- Rebuild the standard PyInstaller bootloader from the official 6.22.3 source archive, verifying its pinned SHA-256 before installation. No obfuscation or protection disabling.
- Add Windows product/file version information identifying GitHug and ISUKA-SSP. This is metadata, not a trusted digital signature.
- Omit generated pyte caches and bundled winpty tests. Runtime native components remain available.
- Include bootloader source provenance and a SHA-256 inventory of packaged files. The inventory excludes itself.
- Repeat Windows source tests, native EXE/PowerShell/recycle/mascot checks and Defender scans of the folder and build ZIP.

Chrome acceptance still requires a download test on the user's machine. No vendor report has been submitted. No trusted signing certificate is available in this build.

References:
- https://support.google.com/chrome/answer/6261569
- https://pyinstaller.org/en/stable/bootloader-building.html
- https://pyinstaller.org/en/stable/usage.html

## GitTotte 1.1.0

The same verified bootloader build and product metadata approach is retained. The product is now GitTotte; settings and credential identifiers retain GitHug for compatibility. The release workflow gates publication on source tests, frozen EXE/bundled Git/terminal smoke checks and Defender folder/ZIP scans. Chrome acceptance still requires the user's download test. No signing or protection bypass is added.
