# source/utils/progress_reporter.py
"""
Progress reporting utility for GUI integration.
Replaces tqdm with callback-based progress updates.
"""

from typing import Optional, Callable, Any, Iterator


class ProgressReporter:
    """
    Context manager for progress reporting that works with GUI.
    Drop-in replacement for tqdm that uses callbacks.
    """
    
    def __init__(
        self,
        iterable: Optional[Any] = None,
        total: Optional[int] = None,
        desc: str = "",
        unit: str = "it",
        callback: Optional[Callable[[int, int, str], None]] = None
    ):
        """
        Args:
            iterable: Iterable to wrap (like tqdm)
            total: Total number of items
            desc: Description prefix
            unit: Unit name (e.g., "frame", "clip")
            callback: Function(current, total, message) for progress updates
        """
        self.iterable = iterable
        self.total = total or (len(iterable) if iterable and hasattr(iterable, "__len__") else 0)
        self.desc = desc
        self.unit = unit
        self.callback = callback
        self.current = 0
        self._last_emitted_bracket = -1  # Track last 10% bracket emitted
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        if self.callback and self.total > 0:
            self.callback(self.total, self.total, f"{self.desc} complete")
    
    def __iter__(self) -> Iterator:
        if self.iterable is None:
            raise ValueError("Cannot iterate without iterable")
        
        for item in self.iterable:
            yield item
            self.update(1)
    
    def update(self, n: int = 1):
        """Update progress by n steps."""
        self.current += n

        if self.callback and self.total > 0:
            pct = int((self.current / self.total) * 100)
            msg = f"{self.desc}: {self.current}/{self.total} {self.unit}"

            # Throttle: emit when crossing into a new 10% bracket or at completion
            # This ensures updates at 0-10%, 10-20%, etc. regardless of exact percentages
            current_bracket = pct // 10
            should_emit = (
                current_bracket > self._last_emitted_bracket or  # Crossed into new bracket
                self.current == self.total or                    # Completion
                self._last_emitted_bracket < 0                   # First update
            )

            if should_emit:
                self._last_emitted_bracket = current_bracket
                self.callback(self.current, self.total, msg)
    
    def close(self):
        """Close progress reporter."""
        if self.callback and self.total > 0:
            self.callback(self.total, self.total, f"{self.desc} complete")


# Global callback registry
_progress_callback: Optional[Callable[[int, int, str], None]] = None


def set_progress_callback(callback: Callable[[int, int, str], None]):
    """Set global progress callback for all ProgressReporter instances."""
    global _progress_callback
    _progress_callback = callback


def get_progress_callback() -> Optional[Callable[[int, int, str], None]]:
    """Get current progress callback."""
    return _progress_callback


def progress_iter(
    iterable: Any,
    desc: str = "",
    unit: str = "it",
    total: Optional[int] = None
) -> Iterator:
    """
    Iterate with progress reporting.
    Drop-in replacement for tqdm().
    
    Usage:
        for item in progress_iter(items, desc="Processing", unit="item"):
            process(item)
    """
    reporter = ProgressReporter(
        iterable=iterable,
        total=total,
        desc=desc,
        unit=unit,
        callback=_progress_callback
    )
    
    with reporter:
        for item in reporter:
            yield item


def report_progress(current: int, total: int, message: str = ""):
    """
    Report progress for non-iterable tasks.
    
    Usage:
        report_progress(1, 3, "Loading data...")
        # ... do work ...
        report_progress(2, 3, "Processing...")
        # ... do work ...
        report_progress(3, 3, "Complete")
    
    Args:
        current: Current step number
        total: Total number of steps
        message: Status message to display
    """
    callback = get_progress_callback()
    if callback:
        callback(current, total, message)


def with_progress(step_name: str):
    """
    Decorator to wrap entire step with progress context.
    
    Usage:
        @with_progress("extract")
        def run():
            # ... step logic ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            report_progress(0, 100, f"{step_name} starting...")
            try:
                result = func(*args, **kwargs)
                report_progress(100, 100, f"{step_name} complete")
                return result
            except Exception as e:
                report_progress(0, 100, f"{step_name} failed: {str(e)}")
                raise
        return wrapper
    return decorator
