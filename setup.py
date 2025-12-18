"""
Setup script for creating macOS .app bundle
Usage: python3 setup.py py2app
"""
from setuptools import setup

APP = ['run_gui.py']
DATA_FILES = [
    ('assets', ['assets/intro.mp3', 'assets/outro.mp3', 'assets/velo_films.png']),
    ('assets/music', [
        'assets/music/blaze_001.mp3',
        'assets/music/blaze_002.mp3',
        'assets/music/blaze_003.mp3',
        'assets/music/blaze_004.mp3',
        'assets/music/heavy_001.mp3',
        'assets/music/heavy_002.mp3',
        'assets/music/heavy_003.mp3',
        'assets/music/heavy_004.mp3',
        'assets/music/throng_001.mp3',
        'assets/music/throng_002.mp3',
        'assets/music/throng_003.mp3',
    ]),
    ('', ['yolov8n.pt', 'yolov8s.pt']),
]

OPTIONS = {
    'argv_emulation': False,
    'packages': ['source'],
    'includes': [
        'PySide6.QtCore',
        'PySide6.QtWidgets', 
        'PySide6.QtGui',
        'matplotlib',
        'cv2',
        'torch',
    ],
    'excludes': ['tkinter', 'test', 'distutils'],
    'plist': {
        'CFBundleName': 'Highlights',
        'CFBundleDisplayName': 'Cycliq Highlights',
        'CFBundleIdentifier': 'com.velofilms.highlights',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
    },
    'iconfile': 'assets/velo_films.png',  # Will convert to .icns if needed
}

setup(
    name='Highlights',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
