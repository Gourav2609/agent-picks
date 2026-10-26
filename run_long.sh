#!/bin/bash
# Long sampling run: one collector process + a memory watchdog, then rebuild report and charts.
# Launch: nohup caffeinate -i ./run_long.sh > data/launcher.log 2>&1 &
# Stop cleanly: touch out/STOP
# If the collector dies on an unexpected error it is restarted (up to 5 times); the cache makes
# the restart continue where it stopped.
cd "$(dirname "$0")" || exit 1
TARGET=${TARGET:-50000}
for attempt in 1 2 3 4 5 6; do
  python3 collect.py --minutes 900 --max-calls 60000 --target-prs "$TARGET" >> data/collector.out 2>&1 &
  PY=$!
  echo "$(date -u +%FT%TZ) collector pid $PY target $TARGET (attempt $attempt)"
  killed=0
  while kill -0 "$PY" 2>/dev/null; do
    rss_kb=$(ps -o rss= -p "$PY" | tr -d ' ')
    if [ "${rss_kb:-0}" -gt 6291456 ]; then
      echo "$(date -u +%FT%TZ) watchdog: rss ${rss_kb} KB over 6 GB, killing $PY"
      kill "$PY"; sleep 10; kill -9 "$PY" 2>/dev/null; killed=1
    fi
    sleep 15
  done
  wait "$PY"; code=$?
  echo "$(date -u +%FT%TZ) collector exited with $code"
  if [ "$killed" = 1 ] || [ -f out/STOP ] || ! grep -q '"stop_reason": "error' data/run.json; then
    break
  fi
  echo "$(date -u +%FT%TZ) restarting after error in 60 s"
  sleep 60
done
python3 report.py && UV_INDEX_URL=https://pypi.org/simple UV_EXTRA_INDEX_URL= command uv run --no-config --with matplotlib python chart.py
echo "$(date -u +%FT%TZ) done"
