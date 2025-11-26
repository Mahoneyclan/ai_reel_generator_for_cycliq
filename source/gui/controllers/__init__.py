# source/gui/controllers/__init__.py
"""
GUI controller modules for main window.

Separates concerns:
- project_controller: Project CRUD and validation
- pipeline_controller: Step execution coordination
- ui_builder: Widget creation and styling
"""

from .project_controller import ProjectController
from .pipeline_controller import PipelineController
from .ui_builder import UIBuilder

__all__ = [
    "ProjectController",
    "PipelineController",
    "UIBuilder",
]