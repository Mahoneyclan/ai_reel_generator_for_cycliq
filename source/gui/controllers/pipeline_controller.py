# source/gui/controllers/pipeline_controller.py
"""
Pipeline execution controller.
Coordinates step execution with progress callbacks.
"""

from pathlib import Path
from typing import Optional, Callable, Set

from ...core.pipeline_executor import PipelineExecutor
from ...io_paths import extract_path, enrich_path, select_path


class PipelineController:
    """Manages pipeline step execution and state."""
    
    def __init__(self, 
                 on_step_started: Optional[Callable] = None,
                 on_step_progress: Optional[Callable] = None,
                 on_step_completed: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        """
        Initialize pipeline controller.
        
        Args:
            on_step_started: Callback(step_name)
            on_step_progress: Callback(step_name, progress, status)
            on_step_completed: Callback(step_name, result)
            on_error: Callback(step_name, error_message)
        """
        self.executor = PipelineExecutor(
            on_step_started=on_step_started,
            on_step_progress=on_step_progress,
            on_step_completed=on_step_completed,
            on_error=on_error
        )
        self.completed_steps: Set[str] = set()
        self.current_project: Optional[Path] = None
    
    def set_current_project(self, project_path: Path):
        """Set the current project for pipeline operations."""
        self.current_project = project_path
    
    def run_prepare(self):
        """Run extraction step."""
        if not self.current_project:
            raise ValueError("No project selected")
        self.executor.prepare()
    
    def run_enrich(self):
        """Run enrichment step: detection, scoring, telemetry."""
        if not self.current_project:
            raise ValueError("No project selected")
        self.executor.enrich()
    
    def run_select(self):
        """Run selection step with manual review."""
        if not self.current_project:
            raise ValueError("No project selected")
        self.executor.select(self.current_project)
    
    def run_build(self):
        """Run finalization steps: build → splash → concat."""
        if not self.current_project:
            raise ValueError("No project selected")
        self.executor.build()
    
    def get_step_status(self) -> dict:
        """
        Get current pipeline step completion status.
        
        Returns:
            Dict with step completion flags
        """
        return {
            "prepare_done": extract_path().exists(),
            "enrich_done": enrich_path().exists(),
            "select_done": select_path().exists(),
        }

    def can_run_enrich(self) -> bool:
        """Check if enrich step can be run (prepare must be done)."""
        return extract_path().exists()

    def can_run_select(self) -> bool:
        """Check if select step can be run (enrich must be done)."""
        return enrich_path().exists()
    
    def can_run_finalize(self) -> bool:
        """Check if finalize step can be run (select must be done)."""
        return select_path().exists()