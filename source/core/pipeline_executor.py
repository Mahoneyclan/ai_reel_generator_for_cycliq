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

logger = setup_logger("core.pipeline_executor")


class PipelineExecutor:
    def __init__(self,
                 on_step_started=None,
                 on_step_progress=None,
                 on_step_completed=None,
                 on_error=None):
        self.on_step_started = on_step_started or (lambda x: None)
        self.on_step_progress = on_step_progress or (lambda x, y, z: None)
        self.on_step_completed = on_step_completed or (lambda x, y: None)
        self.on_error = on_error or (lambda x, y: None)

    def _run_step(self, step_name: str):
        """Internal helper to run a single step with callbacks."""
        try:
            self.on_step_started(step_name)
            fn = step_registry.get_step_function(step_name)
            result = fn()
            self.on_step_progress(step_name, 100, "done")
            self.on_step_completed(step_name, result)
            return result
        except Exception as e:
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
