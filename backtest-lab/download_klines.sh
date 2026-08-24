#!/usr/bin/env bash
# Bulk-download Binance USDT-M perp monthly klines from the public archive
# (data.binance.vision — free, unauthenticated, not rate-limited like the API).
# 1m carries taker_buy_volume (the absorption proxy's raw input); 1h builds
# swings/bias. Idempotent: existing non-empty files are skipped.
set -euo pipefail
cd "$(dirname "$0")/data/raw"

SYMBOLS=(BTCUSDT ETHUSDT SOLUSDT)
TFS=(1m 1h)
MONTHS=()
for y in 2024 2025 2026; do
  for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
    [[ "$y-$m" < "2024-08" ]] && continue
    [[ "$y-$m" > "2026-07" ]] && continue
    MONTHS+=("$y-$m")
  done
done

ok=0; skip=0; fail=0
for sym in "${SYMBOLS[@]}"; do
  for tf in "${TFS[@]}"; do
    for mo in "${MONTHS[@]}"; do
      f="${sym}-${tf}-${mo}.zip"
      if [[ -s "$f" ]]; then skip=$((skip+1)); continue; fi
      url="https://data.binance.vision/data/futures/um/monthly/klines/${sym}/${tf}/${f}"
      if curl -fsS --retry 3 --retry-delay 2 -o "$f.part" "$url"; then
        mv "$f.part" "$f"; ok=$((ok+1))
      else
        rm -f "$f.part"; fail=$((fail+1)); echo "FAILED: $f"
      fi
    done
  done
done
echo "downloaded=$ok skipped=$skip failed=$fail"
ls | wc -l
