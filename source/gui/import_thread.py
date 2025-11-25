# source/gui/import_thread.py

from PySide6.QtCore import QThread, Signal
from source.importer.import_clips import run_import

class ImportThread(QThread):
    """A QThread to run the import process in the background."""
    
    log_message = Signal(str, str)  # message, level
    import_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, cameras, ride_date, ride_name, parent=None):
        super().__init__(parent)
        self.cameras = cameras
        self.ride_date = ride_date
        self.ride_name = ride_name

    def run(self):
        """Execute the import process."""
        try:
            run_import(
                self.cameras,
                self.ride_date,
                self.ride_name,
                log_callback=self.log_message.emit
            )
            self.import_finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

