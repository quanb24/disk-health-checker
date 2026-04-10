# Publish Checklist — v0.1.1

Copy-paste launch checklist. Do every step in order.

## 1. Pre-build verification

```bash
cd disk-health-checker
source .venv/bin/activate

# Tests
pytest -q
# Expected: 130 passed

# Version
python3 -m disk_health_checker --version
# Expected: disk-health-checker 0.1.1

# GUI smoke
python3 -m disk_health_checker.gui
# Expected: window opens, drives populate, close manually
```

## 2. Build

```bash
# Clean previous build
rm -rf build dist

# Build .app
pyinstaller disk_health_checker_gui.spec --noconfirm
# Expected: dist/Disk Health Checker.app exists

# Build .dmg
hdiutil create \
  -volname "Disk Health Checker" \
  -srcfolder "dist/Disk Health Checker.app" \
  -ov -format UDZO \
  "dist/DiskHealthChecker-0.1.1.dmg"
# Expected: dist/DiskHealthChecker-0.1.1.dmg (~40-60 MB)
```

## 3. Verify built app

```bash
# Launch .app directly
open "dist/Disk Health Checker.app"
# Verify: window opens, drives listed, scan button visible
# Close app

# Mount and launch from DMG
open "dist/DiskHealthChecker-0.1.1.dmg"
# Drag to Desktop or run from mounted volume
# Verify: app launches, same behavior as above
# Eject DMG
```

## 4. Commit and tag

```bash
git add -A
git status   # Review — no secrets, no .venv, no dist/
git commit -m "v0.1.1: complete backend refactor, GUI, and packaging"
git tag v0.1.1
git push origin main --tags
```

## 5. Create GitHub release

```bash
gh release create v0.1.1 \
  "dist/DiskHealthChecker-0.1.1.dmg" \
  --title "v0.1.1 — Initial Release" \
  --notes-file RELEASE_NOTES.md
```

Or manually via github.com:
1. Go to Releases > Draft a new release
2. Tag: `v0.1.1`
3. Title: `v0.1.1 — Initial Release`
4. Body: paste contents of `RELEASE_NOTES.md`
5. Attach: `DiskHealthChecker-0.1.1.dmg`
6. Publish

## 6. Post-publish verification

```bash
# Download the DMG like a real user
gh release download v0.1.1 --pattern "*.dmg" --dir /tmp/verify
open /tmp/verify/DiskHealthChecker-0.1.1.dmg
# Right-click app > Open (Gatekeeper bypass)
# Verify: launches, scans, shows verdict
```

## Done

- [ ] Tests pass
- [ ] Version correct
- [ ] GUI launches from source
- [ ] .app builds
- [ ] .dmg builds
- [ ] .app launches from dist
- [ ] App launches from mounted DMG
- [ ] Changes committed
- [ ] Tag created
- [ ] GitHub release published
- [ ] DMG attached to release
- [ ] Downloaded DMG verified
