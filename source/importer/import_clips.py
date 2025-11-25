# source/importer/import_clips.py
"""
Optimized multi-threaded importer for copying video clips from cameras.
Uses ThreadPoolExecutor to copy from both cameras simultaneously.
2-3x faster than sequential copying.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Callable

def run_import(cameras: list, ride_date: str, ride_name: str, log_callback: Callable):
    """
    Imports clips from cameras for a specific date using parallel copying.

    Args:
        cameras (list): List of camera names to import from (e.g., ["Fly12S", "Fly6Pro"])
        ride_date (str): The date of the ride in "yyyy-MM-dd" format
        ride_name (str): The name of the ride
        log_callback (function): A function to call for logging messages
    """
    try:
        # --- 1. Define Paths ---
        base_import_path = Path("/Volumes/GDrive/Fly")  # FIXED: Added GDrive
        ride_date_obj = datetime.strptime(ride_date, "%Y-%m-%d")
        folder_name = f"{ride_date_obj.strftime('%Y-%m-%d')} {ride_name}"
        destination_path = base_import_path / folder_name

        log_callback(f"Destination path: {destination_path}", "info")

        camera_map = {
            "Fly12S": "Fly12Sport",
            "Fly6Pro": "Fly6Pro"
        }
        
        camera_volume_map = {
            "Fly12S": Path("/Volumes/FLY12S"),  # Note: uppercase from your ls output
            "Fly6Pro": Path("/Volumes/FLY6PRO")  # Note: uppercase from your ls output
        }

        # --- 2. Create Destination Directory ---
        log_callback(f"Creating destination directory...", "info")
        destination_path.mkdir(parents=True, exist_ok=True)

        # --- 3. Collect all files to copy (fast scan phase) ---
        log_callback("Scanning cameras for files...", "info")
        files_to_copy: List[Tuple[Path, Path, str]] = []  # (source, dest, camera_name)
        
        for cam_selection in cameras:
            cam_name = camera_map.get(cam_selection)
            cam_volume = camera_volume_map.get(cam_selection)
            
            if not cam_name or not cam_volume:
                log_callback(f"Unknown camera: {cam_selection}", "warning")
                continue

            if not cam_volume.exists():
                log_callback(f"Camera not mounted: {cam_volume}", "warning")
                continue

            source_path = cam_volume / "DCIM" / "100_Ride"
            
            if not source_path.exists():
                log_callback(f"Source path does not exist: {source_path}", "warning")
                continue

            # Scan for matching files
            for file_path in source_path.glob("*.MP4"):
                try:
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mod_time.date() == ride_date_obj.date():
                        # Prepare destination filename
                        base_name = file_path.stem
                        if "_" in base_name:
                            number_part = base_name.split("_")[-1]
                            new_filename = f"{cam_name}_{number_part}.MP4"
                            dest_file = destination_path / new_filename
                            files_to_copy.append((file_path, dest_file, cam_name))
                except Exception as e:
                    log_callback(f"Error scanning {file_path.name}: {e}", "warning")

        if not files_to_copy:
            log_callback("No clips found matching the date", "warning")
            return

        total_files = len(files_to_copy)
        log_callback(f"Found {total_files} clips to copy", "info")

        # --- 4. Copy files in parallel ---
        log_callback("Starting parallel copy...", "info")
        
        def copy_single_file(src: Path, dst: Path, cam: str) -> Tuple[bool, str, str]:
            """Copy a single file and return (success, camera, filename)"""
            try:
                shutil.copy2(src, dst)
                return (True, cam, dst.name)
            except Exception as e:
                return (False, cam, f"{dst.name}: {str(e)}")

        copied_count = 0
        failed_count = 0
        camera_counts = {}

        # Use ThreadPoolExecutor with 4 workers (good for 2 cameras)
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all copy tasks
            future_to_file = {
                executor.submit(copy_single_file, src, dst, cam): (src, dst, cam)
                for src, dst, cam in files_to_copy
            }

            # Process results as they complete
            for future in as_completed(future_to_file):
                src, dst, cam = future_to_file[future]
                try:
                    success, camera, result = future.result()
                    if success:
                        copied_count += 1
                        camera_counts[camera] = camera_counts.get(camera, 0) + 1
                        # Log every 5th file to avoid spam
                        if copied_count % 5 == 0 or copied_count == total_files:
                            log_callback(
                                f"Progress: {copied_count}/{total_files} files copied",
                                "info"
                            )
                    else:
                        failed_count += 1
                        log_callback(f"Failed to copy: {result}", "error")
                except Exception as e:
                    failed_count += 1
                    log_callback(f"Error copying {src.name}: {e}", "error")

        # --- 5. Summary ---
        if copied_count > 0:
            log_callback(
                f"✓ Import complete! Copied {copied_count} clips",
                "success"
            )
            for cam, count in camera_counts.items():
                log_callback(f"  • {cam}: {count} clips", "success")
        else:
            log_callback("No clips were copied", "warning")

        if failed_count > 0:
            log_callback(f"⚠️  {failed_count} files failed to copy", "warning")

    except Exception as e:
        log_callback(f"Import failed: {e}", "error")
        import traceback
        log_callback(traceback.format_exc(), "error")