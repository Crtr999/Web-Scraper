#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# CBC Case Scraper — cron installer
#
# Installs a cron job that runs the scraper every weekday at 8:00 AM.
# Run once after confirming the scraper works correctly with --inspect.
#
# Usage:
#   bash setup_cron.sh            # Install / update the cron job
#   bash setup_cron.sh --remove   # Remove the cron job
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
LOG="$SCRIPT_DIR/../cbc_logs/cron.log"
MARKER="# CBC_SCRAPER"

CRON_JOB="0 8 * * 1-5  cd \"$SCRIPT_DIR\" && $PYTHON run.py >> \"$LOG\" 2>&1  $MARKER"
#            │ │ │   └─ Mon–Fri only (change to * for 7 days)
#            │ │ └───── every day of month
#            │ └─────── 8:00 AM
#            └───────── minute 0

if [[ "${1}" == "--remove" ]]; then
    echo "Removing CBC scraper cron job..."
    crontab -l 2>/dev/null | grep -v "$MARKER" | crontab -
    echo "Done. Current crontab:"
    crontab -l 2>/dev/null || echo "(empty)"
    exit 0
fi

echo "Installing cron job..."
echo "  Schedule : every weekday at 8:00 AM"
echo "  Script   : $SCRIPT_DIR/run.py"
echo "  Log      : $LOG"
echo ""

# Remove any existing CBC scraper job, then add the new one.
(crontab -l 2>/dev/null | grep -v "$MARKER"; echo "$CRON_JOB") | crontab -

echo "Done. Active cron jobs:"
crontab -l
