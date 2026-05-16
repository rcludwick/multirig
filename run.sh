#!/usr/bin/env bash
# MultiRig start script
# - Uses 'uv' for Python dependency management
# - Starts the FastAPI app
#


set -euo pipefail

# Configuration
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PROFILE="${PROFILE:-default}"
RELOAD="${RELOAD:-false}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "🚀 Starting MultiRig..."
echo "📍 Host: $HOST"
echo "📍 Port: $PORT"
echo "📍 Profile: $PROFILE"

# Ensure dependencies are installed
if command -v uv >/dev/null 2>&1; then
    echo "📦 Syncing Python dependencies..."
    uv sync
else
    echo "❌ Error: 'uv' is not installed. Please install it first."
    exit 1
fi

# Run the application
RELOAD_FLAG=""
if [ "$RELOAD" = "true" ]; then
    RELOAD_FLAG="--reload"
fi

echo "🎬 Launching MultiRig..."
exec uv run python -m multirig \
    --host "$HOST" \
    --port "$PORT" \
    --profile "$PROFILE" \
    $RELOAD_FLAG \
    --log-level "$LOG_LEVEL"
