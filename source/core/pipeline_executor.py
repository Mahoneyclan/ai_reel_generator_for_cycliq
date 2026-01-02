# source/core/pipeline_executor.py
"""
Unified pipeline executor for the four high-level actions:
Prepare, Analyze, Select, Build.
Each action runs its constituent steps with callbacks.

UPDATED:
- Enforces file-based dependencies before running each step.
"""

from pathlib import Path
from PySide6.QtWidgets import QApplication

from source.core import step_registry
from source.config import DEFAULT_CONFIG as CFG
from source.utils.log import setup_logger
from source.utils.progress_reporter import set_progress_callback

logger = setup_logger("core.pipeline_executor")


class PipelineExecutor:
    def __init__(
        self,
        on_step_started=None,
        on_step_progress=None,  # Expected: (step_name, current, total, message)
        on_step_completed=None,
        on_error=None
    ):
        """
        Args:
            on_step_started: Callback(step_name)
            on_step_progress: Callback(step_name, current, total, message)
            on_step_completed: Callback(step_name, result)
            on_error: Callback(step_name, error_message)
        """
        self.on_step_started = on_step_started or (lambda step_name: None)
        self.on_step_progress = on_step_progress or (lambda step_name, current, total, msg: None)
        self.on_step_completed = on_step_completed or (lambda step_name, result: None)
        self.on_error = on_error or (lambda step_name, error: None)

    # -------------------------------------------------------------------------
    # Dependency enforcement
    # -------------------------------------------------------------------------

    def _check_required_artifacts(self, step_name: str):
        """
        Enforce pipeline dependencies based on required artifacts.

        This maps logical steps to the concrete CSVs/inputs they require.
        If any required artifact is missing, the step will not run.
        """
        from source.io_paths import flatten_path, extract_path, enrich_path, select_path

        # Map step names to the files they require to exist beforehand.
        requirements = {
            # GPX + flatten
            "flatten": [],  # root of the telemetry timeline

            # Camera alignment requires a flattened GPX timeline
            "align": [flatten_path()],

            # Extract requires GPX timeline + offsets
            "extract": [flatten_path()],

            # Analyze requires extracted frame metadata
            "analyze": [extract_path()],

            # Select requires enriched metadata
            "select": [enrich_path()],

            # Build, splash, concat all require a final selection
            "build": [select_path()],
            "splash": [select_path()],
            "concat": [select_path()],
        }

        required_files = requirements.get(step_name, [])
        missing = [p for p in required_files if not p.exists()]

        if missing:
            missing_str = ", ".join(str(m) for m in missing)
            raise RuntimeError(
                f"Cannot run step '{step_name}' because required artifacts are missing: {missing_str}"
            )

    # -------------------------------------------------------------------------
    # Core step runner
    # -------------------------------------------------------------------------

    def _run_step(self, step_name: str):
        """
        Internal helper to run a single step with callbacks,
        injecting the global progress reporter and enforcing dependencies.
        """

        def step_progress_callback(current: int, total: int, message: str):
            # Update GUI progress indicator with descriptive message
            self.on_step_progress(step_name, current, total, message)

            # Also forward progress into activity log (throttled)
            if total and (current % max(1, total // 10) == 0 or current == total):
                pct = int((current / total) * 100)
                logger.info(f"[progress] {step_name}: {pct}% ({current}/{total}) {message}")

            QApplication.processEvents()

        try:
            # NEW: enforce file-based dependencies
            self._check_required_artifacts(step_name)

            # Signal step start
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
            # Ensure the global callback is cleared on error
            set_progress_callback(None)
            logger.error(f"✘ Step {step_name} failed: {e}", exc_info=True)
            self.on_error(step_name, str(e))
            raise

    # -------------------------------------------------------------------------
    # High-level actions
    # -------------------------------------------------------------------------

    def prepare(self):
        """
        Run preparation steps: alignment & extraction.

        Note:
            Flatten is conceptually part of "Get GPX & Flatten" in the GUI,
            and should have been run before calling prepare().
        """
        for step in ["align", "extract"]:
            self._run_step(step)

    def analyze(self):
        """Run analysis only (enrichment, scoring, partner matching)."""
        for step in ["analyze"]:
            self._run_step(step)

    def select(self, project_dir: Path):
        """
        Run AI pre-select, then open manual selection window.

        Args:
            project_dir: Path to current project directory
        """
        self._run_step("select")

        from source.gui.manual_selection_window import ManualSelectionWindow
        dialog = ManualSelectionWindow(project_dir)
        dialog.exec()

    def build(self):
        """
        Run finalization pipeline: build → splash → concat.

        Requires:
            select.csv to exist (final clip decisions).
        """
        for step in ["build", "splash", "concat"]:
            self._run_step(step)
