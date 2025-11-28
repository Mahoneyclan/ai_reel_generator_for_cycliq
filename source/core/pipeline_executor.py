# source/core/pipeline_executor.py
"""
Unified pipeline executor for the four high-level actions:
Prepare, Analyze, Select, Build.
Each action runs its constituent steps with callbacks.
"""

from pathlib import Path
from source.core import step_registry
from source.config import DEFAULT_CONFIG as CFG
from source.utils.log import setup_logger
from source.utils.progress_reporter import set_progress_callback

logger = setup_logger("core.pipeline_executor")


class PipelineExecutor:
    # 1. FIX THE __init__ CALLBACK SIGNATURE (Optional, but safer for clarity)
    # The current lambda is okay, but if you want to be explicit:
    def __init__(self,
                 on_step_started=None,
                 on_step_progress=None, # Expected to take (step_name, current, total)
                 on_step_completed=None,
                 on_error=None):
        self.on_step_started = on_step_started or (lambda x: None)
        # Change the lambda here to accept 3 arguments, matching the new call in _run_step
        self.on_step_progress = on_step_progress or (lambda x, y, z: None)
        self.on_step_completed = on_step_completed or (lambda x, y: None)
        self.on_error = on_error or (lambda x, y: None)

    def _run_step(self, step_name: str):
        """Internal helper to run a single step with callbacks, injecting progress reporter."""
        
        # Define a wrapper function that receives (current, total, message) 
        # but only passes what the GUI expects (step_name, current, total).
        def step_progress_callback(current: int, total: int, message: str):
            # FIX: Dropping 'message' argument to match MainWindow's expected 4 total args (self + 3)
            self.on_step_progress(step_name, current, total) 

        try:
            self.on_step_started(step_name)
            fn = step_registry.get_step_function(step_name)
            
            # Inject the callback globally
            set_progress_callback(step_progress_callback)
            
            result = fn()
            
            # Cleanup the global callback right after the step function returns
            # DELETE all duplicate/incorrect lines here.
            set_progress_callback(None) 
                
            # Signal completion to the GUI
            self.on_step_completed(step_name, result)
            return result
        
        except Exception as e:
            # Ensure cleanup happens even on error
            set_progress_callback(None) 
            logger.error(f"Step {step_name} failed: {e}", exc_info=True)
            self.on_error(step_name, str(e))
            raise

    # --- High-level actions ---

    def prepare(self):
        """Run preflight → flatten → align."""
        for step in ["preflight", "flatten", "align"]:
            self._run_step(step)

    def analyze(self):
        """Run extract → analyze."""
        for step in ["extract", "analyze"]:
            self._run_step(step)

    def select(self, project_dir: Path):
        """Run AI pre-select, then open manual selection window."""
        # Step 1: AI pre-selection
        self._run_step("select")

        # Step 2: Manual review dialog
        from source.gui.manual_selection_window import ManualSelectionWindow
        dialog = ManualSelectionWindow(project_dir)
        dialog.exec()

    def build(self):
        """Run build → splash → concat."""
        for step in ["build", "splash", "concat"]:
            self._run_step(step)
