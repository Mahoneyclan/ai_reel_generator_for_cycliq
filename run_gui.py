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
import logging 
from source.config import Config, DEFAULT_CONFIG

# Add project root to path
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

CONSOLE_LOG_LEVEL = logging.WARNING
logging.basicConfig(
    level=DEFAULT_CONFIG.LOG_LEVEL,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
)

for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.setLevel(CONSOLE_LOG_LEVEL)

        
# High DPI policy must be set before QApplication
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

from source.gui.main_window import MainWindow

def main():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Highlights")
        app.setOrganizationName("Highlights")
        app.setOrganizationDomain("highlights.local")

        # Set up exception hook for Qt thread crashes
        sys.excepthook = handle_exception
        
        window = MainWindow()
        window.show()
        return app.exec()
    
    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)
        return 1

def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler for uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


if __name__ == "__main__":
    sys.exit(main())
