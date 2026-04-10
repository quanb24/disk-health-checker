# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Disk Health Checker GUI.

Build commands:
  macOS:  pyinstaller disk_health_checker_gui.spec
  Linux:  pyinstaller disk_health_checker_gui.spec

The spec produces:
  macOS:  dist/Disk Health Checker.app
  Linux:  dist/disk-health-checker-gui  (single executable)
"""

import os
import sys
import platform

block_cipher = None

# Icon: use assets/icon.icns if it exists, otherwise no icon.
_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(SPEC)), "assets", "icon.icns")
_ICON = _ICON_PATH if os.path.isfile(_ICON_PATH) else None
if _ICON:
    print(f"Using app icon: {_ICON}")
else:
    print("No icon found at assets/icon.icns — building without custom icon.")

a = Analysis(
    ["disk_health_checker_gui.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Backend modules PyInstaller may not trace through dynamic imports
        "disk_health_checker",
        "disk_health_checker.cli",
        "disk_health_checker.checks.smart",
        "disk_health_checker.checks.smart.collector",
        "disk_health_checker.checks.smart.normalize",
        "disk_health_checker.checks.smart.ata",
        "disk_health_checker.checks.smart.nvme",
        "disk_health_checker.checks.smart.errors",
        "disk_health_checker.models.smart_types",
        "disk_health_checker.models.config",
        "disk_health_checker.models.results",
        "disk_health_checker.utils.disks",
        "disk_health_checker.utils.platform",
        "disk_health_checker.core.doctor",
        "disk_health_checker.core.macos_full",
        "disk_health_checker.core.runner",
        "disk_health_checker.gui",
        "disk_health_checker.gui.app",
        "disk_health_checker.gui.main_window",
        "disk_health_checker.gui.theme",
        "disk_health_checker.gui.worker",
        "disk_health_checker.gui.widgets",
        "disk_health_checker.gui.widgets.drive_selector",
        "disk_health_checker.gui.widgets.verdict_banner",
        "disk_health_checker.gui.widgets.findings_list",
        "disk_health_checker.gui.widgets.next_steps_panel",
        # PySide6 plugins
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Strip unused PySide6 modules to reduce bundle size
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetworkAuth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtTest",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
        "PySide6.QtXml",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtQml",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

is_macos = sys.platform == "darwin"

if is_macos:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Disk Health Checker",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,          # No terminal window
        target_arch=None,       # Build for current arch
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="Disk Health Checker",
    )
    app = BUNDLE(
        coll,
        name="Disk Health Checker.app",
        icon=_ICON,
        bundle_identifier="com.quanb24.disk-health-checker",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "CFBundleDisplayName": "Disk Health Checker",
            "NSHighResolutionCapable": True,
        },
    )
else:
    # Linux: single-file executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="disk-health-checker-gui",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
