## TODO

### PENDING

#### P1 - High Priority

[ ] **Selection algorithm tuning**
  - Sampling grid: 5-second intervals may miss peak action
  - Weight tuning: May need adjustment based on results

[ ] **Improve manual_select UI** - Distinguish source video files
  - Add visual separators or labels showing source file boundaries
  - Color coding, section headers, or timeline markers

#### P2 - Medium Priority

[ ] **Asset caching** - Skip re-rendering unchanged minimaps/gauges/elevation
  - Cache with content hashes
  - Check hash before rendering, skip if unchanged

#### P3 - Future / Research

[ ] **iMovie-style timeline selection** - Manual clip selection when algorithm fails
  - Timeline-based scrubbing interface
  - QGraphicsView-based implementation
  - High complexity (~40-60 hours)

---

### COMPLETED (Summary)

#### Core Pipeline
- [x] Hardware codec detection (h264_videotoolbox on Apple Silicon)
- [x] Dynamic worker scaling for parallelism
- [x] Adaptive YOLO batch size based on RAM
- [x] FFmpeg hardware acceleration
- [x] Smooth clip transitions (crossfades)
- [x] Audio normalization (-16 LUFS)

#### Detection & Selection
- [x] Expanded YOLO classes (person, bicycle, car, motorcycle, bus, truck, traffic light, stop sign)
- [x] Single-camera moments allowed (relaxed pairing)
- [x] Zone limit enforcement (start/end zone caps)
- [x] Scene-aware gap reduction

#### Overlays & Rendering
- [x] Parallel minimap/elevation/gauge pre-rendering
- [x] Dynamic gauge rendering (per-second telemetry)
- [x] Distance-based elevation plot
- [x] Single-camera clip rendering (full-width, no PiP)
- [x] Minimap sizing and positioning fixes

#### GUI & Configuration
- [x] Camera Offset Calibration window
- [x] Per-project timezone setting
- [x] Per-camera timezone support with auto-detect
- [x] Candidate fraction in preferences
- [x] Hardware capability detection
- [x] Project archiving (move between AData/GDrive storage)
