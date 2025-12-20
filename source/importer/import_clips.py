# source/importer/import_clips.py
"""
Optimized importer for copying video clips from cameras.
Uses ThreadPoolExecutor with rsync to copy from both cameras simultaneously.
Faster than sequential shutil.copy2.
"""

import subprocess
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Callable


def _format_size(bytes_size: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f}{unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f}TB"


def _format_speed(bytes_per_sec: float) -> str:
    """Format bytes per second into human-readable speed."""
    return f"{_format_size(bytes_per_sec)}/s"


def _rsync_copy(src: Path, dst: Path, cam: str) -> Tuple[bool, str, str, float, int]:
    """
    Copy a single file with rsync and return (success, camera, filename, duration, size).
    
    Returns:
        Tuple of (success, camera, filename, duration_seconds, file_size_bytes)
    """
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        # Get file size before copying
        file_size = src.stat().st_size
        
        # Use simple rsync without progress flags to avoid compatibility issues
        cmd = ["rsync", "-a", str(src), str(dst)]
        
        # Time the copy operation
        start_time = time.time()
        
        # Increased timeout: 10 minutes per file for large video files
        # Calculate dynamic timeout based on file size (assume minimum 5MB/s transfer)
        min_speed = 5 * 1024 * 1024  # 5 MB/s minimum expected speed
        dynamic_timeout = max(300, file_size / min_speed)  # At least 5 minutes, or longer for huge files
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=dynamic_timeout
        )
        
        duration = time.time() - start_time
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return (False, cam, f"{dst.name}: {error_msg}", duration, file_size)
        
        return (True, cam, dst.name, duration, file_size)
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return (False, cam, f"{dst.name}: Timeout - file copy took too long (>{dynamic_timeout:.0f}s)", duration, 0)
    except Exception as e:
        return (False, cam, f"{dst.name}: {str(e)}", 0, 0)


def run_import(cameras: list, ride_date: str, ride_name: str, log_callback: Callable):
    """
    Imports clips from cameras for a specific date using parallel rsync copying.

    Args:
        cameras (list): List of camera names to import from (e.g., ["Fly12S", "Fly6Pro"])
        ride_date (str): The date of the ride in "yyyy-MM-dd" format
        ride_name (str): The name of the ride
        log_callback (function): A function to call for logging messages
    """
    log_callback("=== Starting Import Process ===", "info")
    
    try:
        # --- 1. Define Paths ---
        base_import_path = Path("/Volumes/GDrive/Fly")
        ride_date_obj = datetime.strptime(ride_date, "%Y-%m-%d")
        folder_name = f"{ride_date_obj.strftime('%Y-%m-%d')} {ride_name}"
        destination_path = base_import_path / folder_name

        log_callback(f"Destination path: {destination_path}", "info")

        camera_map = {
            "Fly12S": "Fly12Sport",
            "Fly6Pro": "Fly6Pro"
        }

        camera_volume_map = {
            "Fly12S": Path("/Volumes/FLY12S"),
            "Fly6Pro": Path("/Volumes/FLY6PRO")
        }

        # --- 2. Create Destination Directory ---
        log_callback("Creating destination directory...", "info")
        destination_path.mkdir(parents=True, exist_ok=True)
        log_callback(f"✓ Destination directory ready: {destination_path}", "info")

        # --- 3. Collect all files to copy ---
        log_callback("Scanning cameras for files...", "info")
        files_to_copy: List[Tuple[Path, Path, str]] = []

        for cam_selection in cameras:
            cam_name = camera_map.get(cam_selection)
            cam_volume = camera_volume_map.get(cam_selection)

            if not cam_name or not cam_volume:
                log_callback(f"Unknown camera: {cam_selection}", "warning")
                continue

            log_callback(f"Checking camera: {cam_selection} at {cam_volume}", "info")

            if not cam_volume.exists():
                log_callback(f"Camera not mounted: {cam_volume}", "warning")
                continue

            source_path = cam_volume / "DCIM" / "100_Ride"
            if not source_path.exists():
                log_callback(f"Source path does not exist: {source_path}", "warning")
                continue

            log_callback(f"Scanning {source_path}...", "info")
            file_count = 0
            
            for file_path in source_path.glob("*.MP4"):
                try:
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mod_time.date() == ride_date_obj.date():
                        base_name = file_path.stem
                        if "_" in base_name:
                            number_part = base_name.split("_")[-1]
                            new_filename = f"{cam_name}_{number_part}.MP4"
                            dest_file = destination_path / new_filename
                            files_to_copy.append((file_path, dest_file, cam_name))
                            file_count += 1
                except Exception as e:
                    log_callback(f"Error scanning {file_path.name}: {e}", "warning")
            
            log_callback(f"Found {file_count} files from {cam_selection}", "info")

        if not files_to_copy:
            log_callback("⚠️ No clips found matching the date", "warning")
            log_callback(f"Looking for files from date: {ride_date}", "info")
            return

        total_files = len(files_to_copy)
        log_callback(f"📁 Found {total_files} clips to copy", "info")

        # --- 4. Copy files in parallel with rsync ---
        log_callback("🚀 Starting parallel rsync copy...", "info")

        copied_count = 0
        failed_count = 0
        camera_counts = {}
        total_bytes = 0
        total_duration = 0

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_file = {
                executor.submit(_rsync_copy, src, dst, cam): (src, dst, cam)
                for src, dst, cam in files_to_copy
            }

            for future in as_completed(future_to_file):
                src, dst, cam = future_to_file[future]
                try:
                    success, camera, result, duration, file_size = future.result()
                    if success:
                        copied_count += 1
                        camera_counts[camera] = camera_counts.get(camera, 0) + 1
                        total_bytes += file_size
                        total_duration += duration
                        
                        # Calculate speed for this file
                        speed = file_size / duration if duration > 0 else 0
                        
                        # Log with copy speed
                        log_callback(
                            f"✓ [{copied_count}/{total_files}] {result} "
                            f"({_format_size(file_size)} in {duration:.1f}s @ {_format_speed(speed)})",
                            "info"
                        )
                    else:
                        failed_count += 1
                        log_callback(f"❌ Failed to copy: {result}", "error")
                except Exception as e:
                    failed_count += 1
                    log_callback(f"❌ Error copying {src.name}: {e}", "error")

        # --- 5. Summary ---
        log_callback("=== Import Summary ===", "info")
        
        if copied_count > 0:
            # Calculate overall statistics
            avg_speed = total_bytes / total_duration if total_duration > 0 else 0
            
            log_callback(f"✓ Import complete! Copied {copied_count} clips", "success")
            log_callback(f"📊 Total size: {_format_size(total_bytes)}", "success")
            log_callback(f"⏱️ Total time: {total_duration:.1f}s", "success")
            log_callback(f"⚡ Average speed: {_format_speed(avg_speed)}", "success")
            
            for cam, count in camera_counts.items():
                log_callback(f"  • {cam}: {count} clips", "success")
        else:
            log_callback("⚠️ No clips were copied", "warning")

        if failed_count > 0:
            log_callback(f"⚠️ {failed_count} files failed to copy", "warning")

    except Exception as e:
        log_callback(f"❌ Import failed: {e}", "error")
        import traceback
        log_callback(traceback.format_exc(), "error")