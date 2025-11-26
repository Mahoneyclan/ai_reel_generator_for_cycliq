# source/gui/controllers/project_controller.py
"""
Project management controller.
Handles project creation, loading, validation, and configuration.
"""

from pathlib import Path
from typing import List, Tuple, Optional, Callable

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import reconfigure_loggers


class ProjectController:
    """Manages project CRUD operations and validation."""
    
    def __init__(self, log_callback: Optional[Callable] = None):
        """
        Initialize project controller.
        
        Args:
            log_callback: Function to call for logging (message, level)
        """
        self.current_project: Optional[Path] = None
        self.log = log_callback or (lambda msg, lvl: print(f"[{lvl}] {msg}"))
    
    def get_all_projects(self) -> List[Tuple[str, Path]]:
        """
        Get list of all projects in PROJECTS_ROOT.
        
        Returns:
            List of (project_name, project_path) tuples
        """
        projects = []
        projects_root = CFG.PROJECTS_ROOT
        
        if not projects_root.exists():
            self.log("Projects folder not found", "error")
            return projects
        
        for folder in projects_root.iterdir():
            if folder.is_dir():
                projects.append((folder.name, folder))
        
        return sorted(projects, key=lambda x: x[0])
    
    def select_project(self, project_path: Path) -> bool:
        """
        Select and configure a project.
        
        Args:
            project_path: Path to project folder
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.current_project = project_path
            CFG.RIDE_FOLDER = project_path.name
            
            # Determine source location
            symlink_path = project_path / "source_videos"
            if symlink_path.exists() and symlink_path.is_symlink():
                # Project-local symlink
                CFG.INPUT_BASE_DIR = project_path
                CFG.SOURCE_FOLDER = "source_videos"
                actual_target = symlink_path.resolve()
                self.log(f"Using project-local symlink: {symlink_path} → {actual_target}", "info")
                
            elif (project_path / "source_path.txt").exists():
                # Imported source reference
                source_meta = project_path / "source_path.txt"
                source_path = Path(source_meta.read_text().strip())
                CFG.INPUT_BASE_DIR = source_path.parent
                CFG.SOURCE_FOLDER = source_path.name
                self.log(f"Using imported source: {source_path}", "info")
                
            else:
                # Legacy: project folder is source
                CFG.SOURCE_FOLDER = project_path.name
                self.log("Using project folder as source", "info")
            
            # Reconfigure logging for this project
            reconfigure_loggers()
            
            return True
            
        except Exception as e:
            self.log(f"Failed to select project: {e}", "error")
            return False
    
    def create_project(self, source_folder: Path) -> Optional[Path]:
        """
        Create new project from source folder.
        
        Args:
            source_folder: Path to folder containing video files
            
        Returns:
            Path to created project, or None on failure
        """
        # Validate source folder has videos
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}
        video_files = [
            f for f in source_folder.iterdir()
            if f.is_file() and f.suffix.lower() in video_extensions
        ]
        
        if not video_files:
            self.log("Error: No video files found in source folder", "error")
            return None
        
        # Check for GPX (warning only)
        gpx_files = list(source_folder.glob("*.gpx"))
        if not gpx_files:
            self.log("Warning: No GPX file found in source folder", "warning")
        
        # Create project structure
        project_name = source_folder.name
        project_folder = CFG.PROJECTS_ROOT / project_name
        
        try:
            # Create directories
            project_folder.mkdir(parents=True, exist_ok=True)
            for sub in ["logs", "working", "clips", "frames",
                        "splash_assets", "minimaps", "gauges"]:
                (project_folder / sub).mkdir(exist_ok=True)
            
            # Create symlink to source videos
            video_link = project_folder / "source_videos"
            if not video_link.exists():
                video_link.symlink_to(source_folder)
                self.log(f"Created symlink to source videos: {video_link}", "success")
            
            # Add metadata file linking to source
            metadata_file = project_folder / "source_path.txt"
            metadata_file.write_text(str(source_folder))
            
            self.log(f"Created project: {project_folder}", "success")
            self.log(f"Linked {len(video_files)} video file(s) from source", "info")
            
            return project_folder
            
        except Exception as e:
            self.log(f"Error creating project: {str(e)}", "error")
            return None
    
    def validate_project(self, project_path: Path) -> Tuple[bool, str]:
        """
        Validate project structure and files.
        
        Args:
            project_path: Path to project folder
            
        Returns:
            (is_valid, error_message) tuple
        """
        if not project_path.exists():
            return False, "Project folder does not exist"
        
        # Check required directories
        required_dirs = ["logs", "working", "clips"]
        for dirname in required_dirs:
            if not (project_path / dirname).exists():
                return False, f"Missing required directory: {dirname}"
        
        # Check for source videos
        symlink_path = project_path / "source_videos"
        if symlink_path.exists():
            if not symlink_path.is_symlink():
                return False, "source_videos exists but is not a symlink"
            if not symlink_path.resolve().exists():
                return False, "source_videos symlink is broken"
        
        return True, ""
    
    def get_project_info(self, project_path: Path) -> dict:
        """
        Get project information and statistics.
        
        Args:
            project_path: Path to project folder
            
        Returns:
            Dict with project info (name, source, video_count, etc.)
        """
        info = {
            "name": project_path.name,
            "path": str(project_path),
            "video_count": 0,
            "has_gpx": False,
            "has_extract": False,
            "has_enriched": False,
            "has_select": False,
        }
        
        # Count videos
        symlink_path = project_path / "source_videos"
        if symlink_path.exists() and symlink_path.is_symlink():
            source_path = symlink_path.resolve()
            video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}
            info["video_count"] = len([
                f for f in source_path.iterdir()
                if f.is_file() and f.suffix.lower() in video_extensions
            ])
        
        # Check pipeline progress
        working_dir = project_path / "working"
        if working_dir.exists():
            info["has_extract"] = (working_dir / "extract.csv").exists()
            info["has_enriched"] = (working_dir / "enriched.csv").exists()
            info["has_select"] = (working_dir / "select.csv").exists()
        
        return info