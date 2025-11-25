# run_gui.py
"""
Entry point for launching the GUI application.
Run with: python3 run_gui.py
"""

import os

# --- CRITICAL: must be FIRST, before any other imports ---
os.environ['MPLBACKEND'] = 'Agg'   # Force matplotlib backend
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['QT_MAC_WANTS_LAYER'] = '1'
# ---------------------------------------------------------

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

# High DPI policy must be set before QApplication
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

from source.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Highlights")
    app.setOrganizationName("Highlights")
    app.setOrganizationDomain("highlights.local")

    window = MainWindow()
    window.show()

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
