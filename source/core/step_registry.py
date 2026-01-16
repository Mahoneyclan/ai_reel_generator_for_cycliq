# source/core/step_registry.py
"""
Centralized registry for pipeline steps.
Single source of truth - all step function mappings in one place.
"""

from __future__ import annotations
from typing import Callable, Dict, List

from .. import steps


# Ordered list of all pipeline steps in execution sequence
PIPELINE_SEQUENCE = [
    "flatten",
    "align",
    "extract",
    "enrich",
    "select",
    "build",
    "splash",
    "concat",
]

# Function registry mapping step names to their run functions
_STEP_FUNCTIONS: Dict[str, Callable] = {
    "flatten": steps.flatten.run,
    "align": steps.align.run,
    "extract": steps.extract.run,
    "enrich": steps.enrich.run,
    "select": steps.select.run,
    "build": steps.build.run,
    "splash": steps.splash.run,
    "concat": steps.concat.run,
}


def get_step_function(step_name: str) -> Callable:
    """
    Retrieve the run function for a given step.
    
    Args:
        step_name: Name of the step (e.g., "preflight", "flatten")
        
    Returns:
        Callable function that executes the step
        
    Raises:
        ValueError: If step_name is not registered
    """
    if step_name not in _STEP_FUNCTIONS:
        raise ValueError(
            f"Unknown step: {step_name}. "
            f"Available: {list(_STEP_FUNCTIONS.keys())}"
        )
    return _STEP_FUNCTIONS[step_name]


def get_all_steps() -> List[str]:
    """Get list of all pipeline steps in execution order."""
    return PIPELINE_SEQUENCE.copy()


def get_step_index(step_name: str) -> int:
    """Get 0-based index of step in pipeline."""
    return PIPELINE_SEQUENCE.index(step_name)