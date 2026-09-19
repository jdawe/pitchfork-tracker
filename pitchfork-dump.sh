#!/bin/bash
# Pitchfork review dump — run: ./pitchfork-dump.sh [days]
# Saves to /tmp/pitchfork-reviews.txt
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAYS="${1:-45}"
python3 "$SCRIPT_DIR/pitchfork-reviews.py" "$DAYS" /tmp/pitchfork-reviews.txt
echo "Output: /tmp/pitchfork-reviews.txt"
