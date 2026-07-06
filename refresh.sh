#!/usr/bin/env bash
# One-command refresh: scrape all sources, geocode, rebuild map data, deploy.
set -euo pipefail
cd "$(dirname "$0")"

echo "== Morgan Group map refresh: $(date) =="
.venv/bin/python -m scraper.run

git add site/data geocache.json 2>/dev/null || git add site/data
if git diff --cached --quiet; then
  echo "No new data — map is already current."
  exit 0
fi
git commit -m "data: refresh $(date +%F)"
git push origin main
echo "Pushed. GitHub Pages will redeploy in ~1 minute."
