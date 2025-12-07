# source/gui/gpx_import_window.py
"""
FIXED: Unified GPX import dialog supporting both Strava and Garmin Connect.
- GPX files save to raw source folder (INPUT_DIR)
- Logs write to project logs folder (LOG_DIR)
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QMessageBox,
    QGroupBox, QProgressBar, QLineEdit, QTabWidget, QWidget,
    QFormLayout
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread

from ..utils.log import setup_logger

log = setup_logger("gui.gpx_import")


class GPXImportThread(QThread):
    """Background thread for GPX platform API operations."""
    
    log_message = Signal(str, str)  # message, level
    activities_loaded = Signal(list)  # activities
    gpx_downloaded = Signal(str)  # output_path
    error_occurred = Signal(str)  # error_message
    
    def __init__(self, platform: str, operation: str, **kwargs):
        """
        Args:
            platform: "strava" or "garmin"
            operation: "connect", "load_activities", or "download_gpx"
            **kwargs: Operation-specific parameters
        """
        super().__init__()
        self.platform = platform
        self.operation = operation
        self.kwargs = kwargs
        self.client = None
    
    def run(self):
        """Execute the requested operation."""
        try:
            if self.platform == "strava":
                self._run_strava()
            elif self.platform == "garmin":
                self._run_garmin()
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def _run_strava(self):
        """Execute Strava operations."""
        from ..strava import StravaClient
        
        if self.operation == "connect":
            self.log_message.emit("Connecting to Strava...", "info")
            client = StravaClient(log_callback=self.log_message.emit)
            if client.connect():
                self.kwargs["client_holder"][0] = client
                self.log_message.emit("✓ Connected to Strava", "success")
            else:
                self.error_occurred.emit("Failed to authenticate with Strava")
        
        elif self.operation == "load_activities":
            client = self.kwargs["client"]
            self.log_message.emit("Loading recent activities...", "info")
            activities = client.get_recent_activities(limit=30)
            if activities:
                self.log_message.emit(f"Found {len(activities)} activities", "success")
                self.activities_loaded.emit(activities)
            else:
                self.log_message.emit("No activities found", "warning")
        
        elif self.operation == "download_gpx":
            client = self.kwargs["client"]
            activity_id = self.kwargs["activity_id"]
            output_path = Path(self.kwargs["output_path"])
            
            self.log_message.emit(f"Downloading GPX for activity {activity_id}...", "info")
            if client.download_gpx(activity_id, output_path):
                self.log_message.emit(f"✓ GPX saved to {output_path.name}", "success")
                self.gpx_downloaded.emit(str(output_path))
            else:
                self.error_occurred.emit("Failed to download GPX - check activity privacy settings")
    
    def _run_garmin(self):
        """Execute Garmin operations."""
        from ..garmin import GarminClient
        
        if self.operation == "connect":
            email = self.kwargs["email"]
            password = self.kwargs["password"]
            
            self.log_message.emit("Connecting to Garmin Connect...", "info")
            client = GarminClient(log_callback=self.log_message.emit)
            
            # Try connection
            if client.connect(email, password):
                self.kwargs["client_holder"][0] = client
                self.log_message.emit("✓ Connected to Garmin Connect", "success")
            else:
                self.error_occurred.emit("Failed to authenticate with Garmin Connect")
        
        elif self.operation == "load_activities":
            client = self.kwargs["client"]
            self.log_message.emit("Loading recent activities...", "info")
            activities = client.get_recent_activities(limit=30)
            if activities:
                self.log_message.emit(f"Found {len(activities)} activities", "success")
                self.activities_loaded.emit(activities)
            else:
                self.log_message.emit("No activities found", "warning")
        
        elif self.operation == "download_gpx":
            client = self.kwargs["client"]
            activity_id = self.kwargs["activity_id"]
            output_path = Path(self.kwargs["output_path"])
            
            self.log_message.emit(f"Downloading GPX for activity {activity_id}...", "info")
            if client.download_gpx(activity_id, output_path):
                self.log_message.emit(f"✓ GPX saved to {output_path.name}", "success")
                self.gpx_downloaded.emit(str(output_path))
            else:
                self.error_occurred.emit("Failed to download GPX")


class GPXImportWindow(QDialog):
    """
    FIXED: Unified dialog for importing GPX from Strava or Garmin Connect.
    - Saves GPX to raw source folder (input_dir)
    - Logs to project folder (log_dir)
    """
    
    def __init__(self, project_dir: Path, input_dir: Path, log_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir  # For logging context
        self.input_dir = input_dir      # RAW SOURCE: where GPX should go
        self.log_dir = log_dir          # Project logs folder
        
        self.strava_client = None
        self.garmin_client = None
        self.current_activities = []
        self.current_platform = None
        self.worker_thread: Optional[GPXImportThread] = None
        
        self.setWindowTitle("Import GPX from Strava or Garmin")
        self.setMinimumSize(900, 700)
        self.setModal(True)
        
        self._setup_ui()
        
        # Log initialization
        log.info(f"[gpx_import] Initialized for project: {project_dir.name}")
        log.info(f"[gpx_import] GPX will be saved to: {input_dir}")
        log.info(f"[gpx_import] Logs writing to: {log_dir}")
    
    def _setup_ui(self):
        """Setup dialog UI with tabs for each platform."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Import GPX from GPS Platform")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 600; color: #1a1a1a; margin-bottom: 10px;"
        )
        layout.addWidget(title)
        
        # Info label showing where GPX will be saved
        info = QLabel(f"📍 GPX will be saved to: {self.input_dir.name}/ride.gpx")
        info.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        layout.addWidget(info)
        
        # Platform tabs
        self.tabs = QTabWidget()
        
        # Strava tab
        self.strava_tab = self._create_strava_tab()
        self.tabs.addTab(self.strava_tab, "🟠 Strava")
        
        # Garmin tab
        self.garmin_tab = self._create_garmin_tab()
        self.tabs.addTab(self.garmin_tab, "🔵 Garmin Connect")
        
        layout.addWidget(self.tabs)
        
        # Shared activities list
        activities_label = QLabel("Select Activity:")
        activities_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(activities_label)
        
        self.activities_list = QListWidget()
        self.activities_list.itemSelectionChanged.connect(self._on_activity_selected)
        self.activities_list.setStyleSheet("""
            QListWidget {
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FAFAFA;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #F0F0F0;
            }
            QListWidget::item:selected {
                background-color: #E8F4F8;
                color: #0066CC;
            }
        """)
        layout.addWidget(self.activities_list)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #DDDDDD;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #007AFF;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Log view
        log_label = QLabel("Status Log:")
        log_label.setStyleSheet("font-weight: 600; font-size: 13px; margin-top: 10px;")
        layout.addWidget(log_label)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(120)
        
        # FIXED: Use macOS monospace font
        from PySide6.QtGui import QFont
        font = QFont("Menlo")  # macOS monospace
        if not font.exactMatch():
            font = QFont("Monaco")  # Fallback
        if not font.exactMatch():
            font = QFont("Courier New")  # Last resort
        font.setPointSize(11)
        font.setStyleHint(QFont.Monospace)
        self.log_view.setFont(font)
        
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #E5E5E5;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.log_view)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.download_btn = QPushButton("⬇️ Download GPX")
        self.download_btn.clicked.connect(self._download_gpx)
        self.download_btn.setEnabled(False)
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D7A4F;
                color: white;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #246840;
            }
            QPushButton:disabled {
                background-color: #F5F5F5;
                color: #AAAAAA;
            }
        """)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.download_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
    
    def _create_strava_tab(self) -> QWidget:
        """Create Strava connection tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Info
        info = QLabel(
            "Strava uses OAuth 2.0 authentication.\n"
            "Click Connect to open your browser and authorize access."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 12px; padding: 10px;")
        layout.addWidget(info)
        
        # Connect button
        self.strava_connect_btn = QPushButton("🔗 Connect to Strava")
        self.strava_connect_btn.clicked.connect(self._connect_strava)
        self.strava_connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #FC4C02;
                color: white;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #E34402;
            }
        """)
        layout.addWidget(self.strava_connect_btn)
        
        # Status
        self.strava_status = QLabel("Not connected")
        self.strava_status.setStyleSheet("color: #666; font-size: 12px; padding: 10px;")
        layout.addWidget(self.strava_status)
        
        # Load button
        self.strava_load_btn = QPushButton("📋 Load Recent Activities")
        self.strava_load_btn.clicked.connect(self._load_strava_activities)
        self.strava_load_btn.setEnabled(False)
        layout.addWidget(self.strava_load_btn)
        
        layout.addStretch()
        return tab
    
    def _create_garmin_tab(self) -> QWidget:
        """Create Garmin connection tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Info
        info = QLabel(
            "Garmin Connect uses email/password authentication.\n"
            "Your credentials are stored securely and only used to access your data."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 12px; padding: 10px;")
        layout.addWidget(info)
        
        # Login form
        form = QFormLayout()
        
        self.garmin_email = QLineEdit()
        self.garmin_email.setPlaceholderText("your.email@example.com")
        self.garmin_email.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
            }
        """)
        form.addRow("Email:", self.garmin_email)
        
        self.garmin_password = QLineEdit()
        self.garmin_password.setEchoMode(QLineEdit.Password)
        self.garmin_password.setPlaceholderText("password")
        self.garmin_password.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
            }
        """)
        form.addRow("Password:", self.garmin_password)
        
        layout.addLayout(form)
        
        # Connect button
        self.garmin_connect_btn = QPushButton("🔗 Connect to Garmin")
        self.garmin_connect_btn.clicked.connect(self._connect_garmin)
        self.garmin_connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #007CC3;
                color: white;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #005F94;
            }
        """)
        layout.addWidget(self.garmin_connect_btn)
        
        # Status
        self.garmin_status = QLabel("Not connected")
        self.garmin_status.setStyleSheet("color: #666; font-size: 12px; padding: 10px;")
        layout.addWidget(self.garmin_status)
        
        # Load button
        self.garmin_load_btn = QPushButton("📋 Load Recent Activities")
        self.garmin_load_btn.clicked.connect(self._load_garmin_activities)
        self.garmin_load_btn.setEnabled(False)
        layout.addWidget(self.garmin_load_btn)
        
        layout.addStretch()
        return tab
    
    def _connect_strava(self):
        """Connect to Strava."""
        self.strava_connect_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        client_holder = [None]
        self.worker_thread = GPXImportThread("strava", "connect", client_holder=client_holder)
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.error_occurred.connect(self._on_connection_error)
        self.worker_thread.finished.connect(lambda: self._on_strava_connected(client_holder))
        self.worker_thread.start()
    
    def _on_strava_connected(self, client_holder):
        """Handle successful Strava connection."""
        self.progress_bar.setVisible(False)
        self.strava_client = client_holder[0]
        
        if self.strava_client:
            self.strava_status.setText("✓ Connected to Strava")
            self.strava_status.setStyleSheet("color: #2D7A4F; font-weight: 600;")
            self.strava_load_btn.setEnabled(True)
            self.current_platform = "strava"
            
            # Auto-load activities
            self._load_strava_activities()
        else:
            self.strava_connect_btn.setEnabled(True)
    
    def _connect_garmin(self):
        """Connect to Garmin."""
        email = self.garmin_email.text().strip()
        password = self.garmin_password.text().strip()
        
        if not email or not password:
            QMessageBox.warning(self, "Missing Credentials", "Please enter both email and password.")
            return
        
        # Disable button and show progress
        self.garmin_connect_btn.setEnabled(False)
        self.garmin_email.setEnabled(False)
        self.garmin_password.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        # Clear previous activities
        self.activities_list.clear()
        
        client_holder = [None]
        self.worker_thread = GPXImportThread(
            "garmin", "connect",
            email=email, password=password, client_holder=client_holder
        )
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.error_occurred.connect(self._on_garmin_connection_error)
        self.worker_thread.finished.connect(lambda: self._on_garmin_connected(client_holder))
        self.worker_thread.start()
    
    def _on_garmin_connected(self, client_holder):
        """Handle successful Garmin connection."""
        self.progress_bar.setVisible(False)
        self.garmin_client = client_holder[0]
        
        if self.garmin_client:
            self.garmin_status.setText("✓ Connected to Garmin Connect")
            self.garmin_status.setStyleSheet("color: #2D7A4F; font-weight: 600;")
            self.garmin_load_btn.setEnabled(True)
            self.current_platform = "garmin"
            
            # Auto-load activities
            self._load_garmin_activities()
        else:
            # Re-enable form on failure
            self.garmin_connect_btn.setEnabled(True)
            self.garmin_email.setEnabled(True)
            self.garmin_password.setEnabled(True)
    
    def _on_garmin_connection_error(self, error_msg: str):
        """Handle Garmin connection error."""
        self.progress_bar.setVisible(False)
        
        # Re-enable form
        self.garmin_connect_btn.setEnabled(True)
        self.garmin_email.setEnabled(True)
        self.garmin_password.setEnabled(True)
        
        QMessageBox.critical(
            self, "Connection Failed",
            f"Failed to connect to Garmin Connect:\n\n{error_msg}\n\n"
            "Please check your email and password."
        )
    
    def _on_connection_error(self, error_msg: str):
        """Handle connection error (Strava)."""
        self.progress_bar.setVisible(False)
        self.strava_connect_btn.setEnabled(True)
        
        QMessageBox.critical(
            self, "Connection Failed",
            f"Failed to connect:\n\n{error_msg}"
        )
    
    def _load_strava_activities(self):
        """Load Strava activities."""
        if not self.strava_client:
            return
        
        self.activities_list.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.current_platform = "strava"
        
        self.worker_thread = GPXImportThread("strava", "load_activities", client=self.strava_client)
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.activities_loaded.connect(self._populate_strava_activities)
        self.worker_thread.finished.connect(lambda: self.progress_bar.setVisible(False))
        self.worker_thread.start()
    
    def _load_garmin_activities(self):
        """Load Garmin activities."""
        if not self.garmin_client:
            return
        
        self.activities_list.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.current_platform = "garmin"
        
        self.worker_thread = GPXImportThread("garmin", "load_activities", client=self.garmin_client)
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.activities_loaded.connect(self._populate_garmin_activities)
        self.worker_thread.finished.connect(lambda: self.progress_bar.setVisible(False))
        self.worker_thread.start()
    
    def _populate_strava_activities(self, activities: list):
        """Populate Strava activities list."""
        self.current_activities = activities
        
        for activity in activities:
            # Format display with GPX indicator
            name = activity.get("name", "Unnamed")
            distance = activity.get("distance", 0) / 1000.0
            time_s = activity.get("moving_time", 0)
            hours = time_s // 3600
            minutes = (time_s % 3600) // 60
            
            start_date = activity.get("start_date", "")
            if start_date:
                date_obj = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                date_str = date_obj.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = "Unknown date"
            
            time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            has_gpx = bool(activity.get("start_latlng"))
            gpx_indicator = "📍" if has_gpx else "⚠️ "
            
            display = f"{gpx_indicator} {name}\n{date_str} • {distance:.1f} km • {time_str}"
            
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, activity["id"])
            self.activities_list.addItem(item)
    
    def _populate_garmin_activities(self, activities: list):
        """Populate Garmin activities list."""
        self.current_activities = activities
        
        for activity in activities:
            # Format display
            name = activity.get("activityName", "Unnamed")
            distance_m = activity.get("distance", 0)
            distance_km = distance_m / 1000.0
            duration_s = activity.get("duration", 0)
            
            hours = int(duration_s // 3600)
            minutes = int((duration_s % 3600) // 60)
            
            start_time = activity.get("startTimeLocal", "")
            if start_time:
                try:
                    date_obj = datetime.fromisoformat(start_time.replace("Z", ""))
                    date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                except:
                    date_str = start_time[:16]
            else:
                date_str = "Unknown date"
            
            time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            # Garmin activities always have GPX
            display = f"📍 {name}\n{date_str} • {distance_km:.1f} km • {time_str}"
            
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, activity["activityId"])
            self.activities_list.addItem(item)
    
    def _on_activity_selected(self):
        """Enable download button when activity selected."""
        has_selection = bool(self.activities_list.selectedItems())
        self.download_btn.setEnabled(has_selection and self.current_platform is not None)
    
    def _download_gpx(self):
        """
        FIXED: Download GPX to raw source folder (input_dir).
        """
        selected = self.activities_list.selectedItems()
        if not selected or not self.current_platform:
            return
        
        activity_id = selected[0].data(Qt.UserRole)
        
        # FIXED: Save to raw source folder (INPUT_DIR), not project folder
        output_path = self.input_dir / "ride.gpx"
        
        log.info(f"[gpx_import] Downloading GPX to source folder: {output_path}")
        
        # Confirm overwrite if exists
        if output_path.exists():
            reply = QMessageBox.question(
                self, "Overwrite GPX?",
                f"A GPX file already exists in the source folder:\n\n{output_path}\n\nDo you want to replace it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        client = self.strava_client if self.current_platform == "strava" else self.garmin_client
        
        self.worker_thread = GPXImportThread(
            self.current_platform, "download_gpx",
            client=client, activity_id=activity_id, output_path=str(output_path)
        )
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.gpx_downloaded.connect(self._on_download_complete)
        self.worker_thread.error_occurred.connect(self._on_download_error)
        self.worker_thread.finished.connect(lambda: self.progress_bar.setVisible(False))
        self.worker_thread.start()
    
    def _on_download_complete(self, output_path: str):
        """Handle successful download."""
        self.download_btn.setEnabled(True)
        
        log.info(f"[gpx_import] GPX successfully downloaded to: {output_path}")
        
        QMessageBox.information(
            self, "GPX Downloaded",
            f"✓ GPX file saved successfully to source folder!\n\n"
            f"Location: {Path(output_path).parent.name}/{Path(output_path).name}\n\n"
            f"You can now run the Prepare step."
        )
        
        self.accept()
    
    def _on_download_error(self, error_msg: str):
        """Handle download error."""
        self.download_btn.setEnabled(True)
        
        log.error(f"[gpx_import] Download failed: {error_msg}")
        
        QMessageBox.warning(self, "Download Failed", f"Failed to download GPX:\n\n{error_msg}")
    
    def log(self, message: str, level: str = "info"):
        """
        Add message to log view and project log file.
        """
        color_map = {
            "info": "#333333",
            "error": "#D32F2F",
            "warning": "#F57C00",
            "success": "#2D7A4F"
        }
        
        color = color_map.get(level, "#333333")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Display in UI
        self.log_view.append(
            f'<span style="color: #888">[{timestamp}]</span> '
            f'<span style="color: {color}">{message}</span>'
        )
        self.log_view.ensureCursorVisible()
        
        # Also log to project log file
        log_func = getattr(log, level, log.info)
        log_func(f"[gpx_import] {message}")