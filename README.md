```markdown
# Velo Highlights AI 🚴‍♂️🎬

A macOS-native application and pipeline for generating highlight reels from cycling footage.  
It ingests raw video and GPX data, analyzes frames using AI (YOLO), and produces a polished MP4 reel with overlays, minimaps, gauges, and intro/outro music.

---

## ✨ Features

- **Import Workflow**
  - Import footage from Fly12S and Fly6Pro cameras
  - Associate rides with GPX files and metadata
  - Background import thread with logging

- **Pipeline Execution**
  - Unified executor for four high-level actions:
    1. **Prepare** → Preflight, Flatten, Align
    2. **Analyze** → Extract, AI detection & enrichment
    3. **Select** → AI pre-selection + manual review GUI
    4. **Build** → Render clips, splash maps, concat final reel

- **AI-Powered Analysis**
  - YOLOv5 detection (bicycles, configurable classes)
  - Frame scoring with speed, gradient, bounding box area, scene boosts
  - Candidate selection with GPS filtering and zone penalties

- **Video Rendering**
  - Picture-in-Picture overlays
  - Minimap route visualization
  - HUD gauges (speed, cadence, HR, elevation, gradient)
  - Intro/outro music and splash map

- **macOS GUI**
  - Project management interface
  - Import dialog with camera/date/name selection
  - Preferences window for pipeline tuning
  - Activity log with color-coded messages

---

## 📂 Project Structure

```
source/
├── __init__.py              # Config entrypoint
├── config.py                # Global configuration (paths, weights, encoding)
├── core/                    # Pipeline orchestration
│   ├── __init__.py
│   ├── pipeline_executor.py # High-level executor (prepare, analyze, select, build)
│   ├── step_registry.py     # Central registry of pipeline steps
│   └── models/              # Core dataclasses (Project)
├── gui/                     # macOS GUI (PySide6)
│   ├── __init__.py
│   ├── main_window.py       # Main application window
│   ├── import_window.py     # Import ride dialog
│   ├── import_thread.py     # Background import thread
│   └── preferences_window.py# Preferences dialog
└── steps/                   # Individual pipeline steps (preflight, flatten, etc.)
```

---

## ⚙️ Configuration

All pipeline settings are centralized in `source/config.py`.

Key parameters:
- **Paths**
  - `PROJECTS_ROOT`: `/Volumes/GDrive/Fly_Projects`
  - `INPUT_BASE_DIR`: `/Volumes/GDrive/Fly`
- **Detection**
  - `YOLO_DETECT_CLASSES`: `[1]` (bicycle)
  - `YOLO_MIN_CONFIDENCE`: `0.10`
- **Scoring Weights**
  - `detect_score`: 0.35
  - `speed_kmh`: 0.25
  - `gradient`: 0.10
  - `bbox_area`: 0.10
  - `scene_boost`: 0.20
- **Encoding**
  - `VIDEO_CODEC`: `libx264`
  - `BITRATE`: `8M`

Override preferences via the GUI Preferences window or by editing `config.py`.

---

## 🚀 Usage

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

Dependencies include:
- `PySide6` (GUI)
- `torch` (YOLO + MPS acceleration)
- `opencv-python`
- `ffmpeg`

### 2. Launch Application
```bash
python -m source.gui.main_window
```

### 3. Workflow
1. **Create Project** → Select source folder with videos + GPX
2. **Import Clips** → Use Import dialog for camera/date/name
3. **Run Pipeline Steps**:
   - Prepare → Analyze → Select → Build
4. **Review Clips** → Manual selection window
5. **Finalize Reel** → Outputs MP4 with overlays

---

## 🖥️ GUI Overview

- **Left Panel** → Project list, create/import/preferences
- **Right Panel** → Pipeline step buttons, progress bar, activity log
- **Dialogs**:
  - ImportRideWindow → Import new ride footage
  - PreferencesWindow → Adjust pipeline parameters

---

## 📊 Pipeline Steps

| Step       | Description                                      |
|------------|--------------------------------------------------|
| Preflight  | Validate inputs, parse GPX                       |
| Flatten    | Normalize video structure                        |
| Align      | Sync camera timestamps with GPX                  |
| Extract    | Sample frames at configured FPS                  |
| Analyze    | Run YOLO detection + enrich metadata             |
| Select     | AI candidate selection + manual review           |
| Build      | Render clips with overlays                       |
| Splash     | Generate splash map                              |
| Concat     | Assemble final MP4 reel                          |

---

## 🛠️ Development Notes

- Optimized for Apple Silicon (M1/M2) with Metal Performance Shaders (`USE_MPS=True`)
- Hardware-accelerated encoding via `videotoolbox`
- Modular step registry for easy extension
- Logging integrated with GUI (color-coded messages)

---

## 📄 License

This project is proprietary to the author.  
For inquiries about usage or distribution, please contact the maintainer.

---


## 🧭 Credits

Developed as a hobby for cyclists who want effortless highlight reels of their rides.  
Built with ❤️ using Python, PySide6, YOLO, and ffmpeg.
```
