#!/usr/bin/env bash
set -euo pipefail

# Render runs this during each deploy, so the published dashboard contains a
# fresh snapshot. Set RENDER_SKIP_SCRAPE=1 for a fast local packaging check.
if [[ "${RENDER_SKIP_SCRAPE:-0}" != "1" ]]; then
  python3 enhanced_scraper.py
fi

rm -rf dist
mkdir -p dist
cp dashboard.html dashboard_data.js dist/
printf 'Published dashboard assets:\n'
find dist -maxdepth 1 -type f -printf '  %f\n' | sort
