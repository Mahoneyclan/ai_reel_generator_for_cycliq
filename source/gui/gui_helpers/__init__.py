# source/gui/gui_helpers/__init__.py
"""
GUI helper modules for main window.

Separates concerns into focused, testable components:
- panels: UI panel widgets (project list, pipeline, actions, log)
- managers: Cross-cutting concerns (status, dialogs, tracking)
"""

from .project_list_panel import ProjectListPanel
from .pipeline_panel import PipelinePanel
from .action_button_panel import ActionButtonPanel
from .activity_log_panel import ActivityLogPanel
from .status_manager import StatusManager
from .dialog_manager import DialogManager
from .step_status_tracker import StepStatusTracker

__all__ = [
    "ProjectListPanel",
    "PipelinePanel",
    "ActionButtonPanel",
    "ActivityLogPanel",
    "StatusManager",
    "DialogManager",
    "StepStatusTracker",
]