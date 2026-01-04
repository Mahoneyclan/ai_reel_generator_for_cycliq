#!/bin/bash
# install.sh - One-time setup for Velo Highlights AI
# Run this once after cloning the repository

set -e  # Exit on error

echo "========================================"
echo "  Velo Highlights AI - Installation"
echo "========================================"
echo ""

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# 1. Check for Homebrew
echo "[1/4] Checking Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "  Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "  Homebrew found"
fi

# 2. Install FFmpeg
echo ""
echo "[2/4] Checking FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "  Installing FFmpeg..."
    brew install ffmpeg
else
    echo "  FFmpeg found: $(ffmpeg -version | head -1)"
fi

# 3. Create virtual environment
echo ""
echo "[3/4] Setting up Python environment..."
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv .venv
else
    echo "  Virtual environment exists"
fi

source .venv/bin/activate

# 4. Install Python dependencies
echo ""
echo "[4/4] Installing Python packages..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "To run the app:"
echo "  1. Double-click 'Velo Highlights AI' on your Desktop"
echo "  2. Or run: ./run.sh"
echo ""
echo "Creating desktop shortcut..."
./create_shortcut.sh

echo ""
echo "Done!"
