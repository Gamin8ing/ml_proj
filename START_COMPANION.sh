#!/bin/bash
# Quick start script for CAIGA companion

cd "$(dirname "$0")"

echo "🎮 Starting CAIGA Companion..."
echo "📁 Working directory: $(pwd)"
echo "🔧 Config: companion/config.env"
echo ""

# Check if port is already in use
PORT=$(grep COMPANION_PORT companion/config.env | cut -d= -f2)
PORT=${PORT:-5001}

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port $PORT is already in use!"
    echo "   Stop the existing service or change COMPANION_PORT in config.env"
    exit 1
fi

# Start the companion
echo "🚀 Starting companion on port $PORT..."
python -m companion.companion_server
