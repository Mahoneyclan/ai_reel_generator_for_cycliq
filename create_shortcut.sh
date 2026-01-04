#!/bin/bash
# create_shortcut.sh - Create a clickable desktop app

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
APP_NAME="Velo Highlights AI"
DESKTOP_APP="$HOME/Desktop/${APP_NAME}.app"

echo "Creating desktop shortcut..."

# Remove existing
rm -rf "$DESKTOP_APP"

# Create .app bundle structure
mkdir -p "$DESKTOP_APP/Contents/MacOS"
mkdir -p "$DESKTOP_APP/Contents/Resources"

# Create the launcher script
cat > "$DESKTOP_APP/Contents/MacOS/launcher" << EOF
#!/bin/bash
cd "$PROJECT_DIR"
source .venv/bin/activate
python run_gui.py
EOF

chmod +x "$DESKTOP_APP/Contents/MacOS/launcher"

# Create Info.plist
cat > "$DESKTOP_APP/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.velofilms.highlights</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

# Copy icon if it exists
if [ -f "$PROJECT_DIR/assets/icon.icns" ]; then
    cp "$PROJECT_DIR/assets/icon.icns" "$DESKTOP_APP/Contents/Resources/AppIcon.icns"
    # Update plist to use icon
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$DESKTOP_APP/Contents/Info.plist" 2>/dev/null || true
fi

echo "Created: $DESKTOP_APP"
echo ""
echo "You can now double-click 'Velo Highlights AI' on your Desktop!"
