#!/usr/bin/env bash
# ==============================================================================
# Octopus Agent: Mac Mini Production Deployment & Environment Setup
# Optimized for Apple Silicon (M1/M2/M3/M4) Hardware Acceleration
# ==============================================================================

set -e

echo "🐙 ========================================================"
echo "🐙 OCTOPUS AGENT: Mac Mini Production Environment Setup"
echo "🐙 ========================================================"

# 1. Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "📦 Homebrew not detected. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    echo "✅ Homebrew detected."
fi

# 2. Install FFmpeg with Apple Silicon VideoToolbox Hardware Acceleration
echo "🎥 Installing FFmpeg with VideoToolbox hardware encoder..."
brew install ffmpeg

# Verify VideoToolbox support
if ffmpeg -encoders 2>&1 | grep -q "h264_videotoolbox"; then
    echo "⚡ [SUCCESS] Apple Silicon VideoToolbox hardware encoder detected!"
else
    echo "⚠️ VideoToolbox encoder not found. Using default CPU encoder."
fi

# 3. Install Python 3.11 & Git
echo "🐍 Ensuring Python 3.11 is installed..."
brew install python@3.11 git

# 4. Create Virtual Environment
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

echo "📂 Project root: $PROJECT_DIR"

if [ ! -d "venv" ]; then
    echo "🌱 Creating Python virtual environment (venv)..."
    python3.11 -m venv venv
fi

echo "📦 Activating venv and upgrading pip..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel

# 5. Install Python Dependencies
echo "📥 Installing Octopus Agent dependencies..."
pip install -r requirements.txt

# 6. Ensure .env exists
if [ ! -f ".env" ]; then
    echo "📝 Creating initial .env from .env.example..."
    cp .env.example .env
fi

# 7. Setup macOS launchd 24/7 background service
PLIST_NAME="com.octopus.agent.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/logs"

# Generate dynamically configured plist with exact paths
cat <<EOF > "$LAUNCH_AGENTS_DIR/$PLIST_NAME"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.octopus.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>server:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF

echo "🚀 Service configuration written to $LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo ""
echo "🐙 ========================================================"
echo "✅ OCTOPUS AGENT SETUP COMPLETE ON MAC MINI!"
echo "🐙 ========================================================"
echo ""
echo "To start the agent in background 24/7 immediately:"
echo "   launchctl load -w $LAUNCH_AGENTS_DIR/$PLIST_NAME"
echo ""
echo "To check live server logs:"
echo "   tail -f $PROJECT_DIR/logs/launchd_stdout.log"
echo ""
echo "To stop the agent:"
echo "   launchctl unload -w $LAUNCH_AGENTS_DIR/$PLIST_NAME"
echo ""
echo "Web Dashboard will be live at: http://localhost:8000"
echo "Telegram remote command room is active 24/7!"
