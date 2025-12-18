# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('yolov8n.pt', '.'), ('yolov8s.pt', '.')],
    hiddenimports=['PySide6', 'cv2', 'torch', 'ultralytics'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Highlights',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Highlights',
)
app = BUNDLE(
    coll,
    name='Highlights.app',
    icon=None,
    bundle_identifier='com.velofilms.highlights',
)
