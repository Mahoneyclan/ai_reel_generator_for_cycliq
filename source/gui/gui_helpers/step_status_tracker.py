# source/gui/helpers/step_status_tracker.py
"""
Pipeline step status tracker.
Tracks which steps have been completed.
"""

from typing import Set


class StepStatusTracker:
    """Tracks completion status of pipeline steps."""
    
    def __init__(self):
        """Initialize empty tracker."""
        self.completed_steps: Set[str] = set()
    
    def mark_completed(self, step_name: str):
        """
        Mark a step as completed.
        
        Args:
            step_name: Name of completed step
        """
        self.completed_steps.add(step_name)
    
    def is_completed(self, step_name: str) -> bool:
        """
        Check if step is completed.
        
        Args:
            step_name: Step name to check
            
        Returns:
            True if step is marked complete
        """
        return step_name in self.completed_steps
    
    def reset(self):
        """Clear all completion status."""
        self.completed_steps.clear()
    
    def get_completion_count(self) -> int:
        """Get number of completed steps."""
        return len(self.completed_steps)