# App Assets

## Icon

Place your app icon here as `icon.icns` (macOS) and/or `icon.png` (Linux/general).

### How to create `icon.icns` from a PNG

1. Prepare a 1024x1024 PNG named `icon.png`
2. Create the iconset:
   ```bash
   mkdir icon.iconset
   sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
   sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
   sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
   sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
   sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
   sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
   sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
   sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
   sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
   sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
   iconutil -c icns icon.iconset
   ```
3. Move `icon.icns` into this directory
4. Rebuild: `pyinstaller disk_health_checker_gui.spec --noconfirm`

The PyInstaller spec automatically uses `assets/icon.icns` when present.
