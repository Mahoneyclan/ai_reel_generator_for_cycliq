# source/core/pipeline_executor.py
"""
Unified pipeline executor for the four high-level actions:
Prepare, Analyze, Select, Build.
Each action runs its constituent steps with callbacks.
"""

from pathlib import Path
from PySide6.QtWidgets import QApplication

from source.core import step_registry
from source.config import DEFAULT_CONFIG as CFG
from source.utils.log import setup_logger
from source.utils.progress_reporter import set_progress_callback

logger = setup_logger("core.pipeline_executor")


class PipelineExecutor:
    def __init__(self,
                 on_step_started=None,
                 on_step_progress=None,  # Expected: (step_name, current, total)
                 on_step_completed=None,
                 on_error=None):
        self.on_step_started = on_step_started or (lambda x: None)
        self.on_step_progress = on_step_progress or (lambda x, y, z: None)
        self.on_step_completed = on_step_completed or (lambda x, y: None)
        self.on_error = on_error or (lambda x, y: None)

    def _run_step(self, step_name: str):
        """Internal helper to run a single step with callbacks, injecting progress reporter."""

        def step_progress_callback(current: int, total: int, message: str):
            # Update GUI progress indicator with descriptive message
            self.on_step_progress(step_name, current, total, message)

            # Also forward progress into activity log (throttled)
            if total and (current % max(1, total // 10) == 0 or current == total):
                pct = int((current / total) * 100)
                logger.info(f"[progress] {step_name}: {pct}% ({current}/{total}) {message}")

            QApplication.processEvents()


        try:
            # Reset progress indicator at start
            self.on_step_started(step_name)
            logger.info(f"▶ Starting step: {step_name}")

            fn = step_registry.get_step_function(step_name)

            # Inject the callback globally
            set_progress_callback(step_progress_callback)

            result = fn()

            # Cleanup the global callback
            set_progress_callback(None)

            # Signal completion to the GUI
            self.on_step_completed(step_name, result)
            logger.info(f"✓ Completed step: {step_name}")
            return result

        except Exception as e:
            set_progress_callback(None)
            logger.error(f"❌ Step {step_name} failed: {e}", exc_info=True)
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
        self._run_step("select")

        from source.gui.manual_selection_window import ManualSelectionWindow
        dialog = ManualSelectionWindow(project_dir)
        dialog.exec()

    def build(self):
        """Run build → splash → concat."""
        for step in ["build", "splash", "concat"]:
            self._run_step(step)
