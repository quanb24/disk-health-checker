# Build Instructions

Step-by-step commands to build and package Disk Health Checker.

## Prerequisites

- Python 3.11+
- macOS 13+ (for .app and .dmg) or Linux
- `smartctl` installed (`brew install smartmontools` / `sudo apt install smartmontools`)

## Setup

```bash
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gui,dev]"
pip install pyinstaller
```

## Run tests

```bash
pytest -q
```

## Build macOS .app

```bash
pyinstaller disk_health_checker_gui.spec --noconfirm
```

Output: `dist/Disk Health Checker.app`

Test it:

```bash
open "dist/Disk Health Checker.app"
```

## Build macOS .dmg

After the `.app` is built:

```bash
# Clean any previous DMG
rm -f "dist/DiskHealthChecker-0.1.1.dmg"

# Create DMG with hdiutil (built into macOS, no extra tools)
hdiutil create \
  -volname "Disk Health Checker" \
  -srcfolder "dist/Disk Health Checker.app" \
  -ov \
  -format UDZO \
  "dist/DiskHealthChecker-0.1.1.dmg"
```

Output: `dist/DiskHealthChecker-0.1.1.dmg` (~40-60 MB)

To test:

```bash
open "dist/DiskHealthChecker-0.1.1.dmg"
# Drag "Disk Health Checker" to Applications (or run from the mounted volume)
```

## Build Linux executable

```bash
pyinstaller disk_health_checker_gui.spec --noconfirm
```

Output: `dist/disk-health-checker-gui`

Test it:

```bash
./dist/disk-health-checker-gui
```

## Adding an app icon (optional)

1. Create a 1024x1024 PNG and save it as `assets/icon.png`
2. Convert to `.icns`:
   ```bash
   mkdir icon.iconset
   sips -z 16 16     assets/icon.png --out icon.iconset/icon_16x16.png
   sips -z 32 32     assets/icon.png --out icon.iconset/icon_16x16@2x.png
   sips -z 32 32     assets/icon.png --out icon.iconset/icon_32x32.png
   sips -z 64 64     assets/icon.png --out icon.iconset/icon_32x32@2x.png
   sips -z 128 128   assets/icon.png --out icon.iconset/icon_128x128.png
   sips -z 256 256   assets/icon.png --out icon.iconset/icon_128x128@2x.png
   sips -z 256 256   assets/icon.png --out icon.iconset/icon_256x256.png
   sips -z 512 512   assets/icon.png --out icon.iconset/icon_256x256@2x.png
   sips -z 512 512   assets/icon.png --out icon.iconset/icon_512x512.png
   sips -z 1024 1024 assets/icon.png --out icon.iconset/icon_512x512@2x.png
   iconutil -c icns icon.iconset
   mv icon.icns assets/icon.icns
   rm -rf icon.iconset
   ```
3. Rebuild: `pyinstaller disk_health_checker_gui.spec --noconfirm`

The spec detects `assets/icon.icns` automatically.

## Release checklist

1. `pytest -q` — all tests pass
2. `python3 -m disk_health_checker --version` — version correct
3. `python3 -m disk_health_checker.gui` — GUI launches
4. `pyinstaller disk_health_checker_gui.spec --noconfirm` — build succeeds
5. `open "dist/Disk Health Checker.app"` — app launches, scan works
6. `hdiutil create ...` — DMG created
7. Mount DMG, run app from mounted volume — works
8. Attach DMG to GitHub release
