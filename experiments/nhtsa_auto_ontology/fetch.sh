#!/usr/bin/env bash
# Fetch NHTSA recalls and complaints for Chevrolet Bolt EV / EUV 2017-2023 into ./raw (public API, no key).
set -euo pipefail
cd "$(dirname "$0")" && mkdir -p raw
for y in 2017 2018 2019 2020 2021 2022 2023; do
  for m in bolt_ev bolt_euv; do
    q="make=chevrolet&model=${m/_/%20}&modelYear=$y"
    curl -sf -m 90 -o "raw/rcl_${m}_$y.json" "https://api.nhtsa.gov/recalls/recallsByVehicle?$q"
    curl -sf -m 90 -o "raw/cmp_${m}_$y.json" "https://api.nhtsa.gov/complaints/complaintsByVehicle?$q"
  done
done
