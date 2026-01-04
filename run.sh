#!/bin/bash
# run.sh - Launch Velo Highlights AI

cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Run the GUI
python run_gui.py
