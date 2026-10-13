<div align="center">

# Recollect

**A quiet timeline of your workday.**

Recollect captures periodic snapshots of your Windows desktop and organizes them into a searchable activity timeline. Your screenshots and activity database stay on your computer.

[Download for Windows](https://github.com/kargalar/recollect/releases/latest) · [Build from source](#build-from-source) · [Report an issue](https://github.com/kargalar/recollect/issues)

</div>

## Features

- Capture the active desktop at a configurable interval.
- Browse and search a local timeline with app and window details.
- Pause capture automatically while the computer is idle.
- Run quietly from the Windows system tray.
- Store screenshots and the activity database locally.

## Download and run

Download `Recollect-Windows-x64.zip` from [Releases](https://github.com/kargalar/recollect/releases/latest), extract it into a writable folder, and run `Recollect.exe`. The app opens its local timeline in your browser. Keep the API and recorder executables next to the launcher.

Recollect records desktop screenshots. Review the capture folder and settings before enabling it, and protect the files with your Windows account permissions.

## Build from source

Requirements: Windows 10 or later, Python 3.12+, Tesseract OCR for text recognition, and the packages in `requirements.txt`.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app\tray.py
```

For a packaged release, install PyInstaller and run `build.ps1`. The build creates `Recollect.exe`, `RecollectApi.exe`, and `RecollectRecorder.exe` under `dist/`.

## Privacy

Screenshots, OCR text, window titles, and activity metadata can be sensitive. They are stored locally by default. Do not upload your database, capture images, or local configuration when reporting an issue.

## License

Recollect is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
