#!/data/data/com.termux/files/usr/bin/bash
# usage: ./pull_report.sh <job_id> <name>
#   e.g. ./pull_report.sh d0491d399078426b8aa4ba66a668971c studio-01
set -e
JOB="$1"; NAME="${2:-$1}"
cd ~/WrattyGstudio2
mkdir -p bench
modal volume get "wratty-mixes" "reports/${JOB}.json" "./bench/${NAME}.json"
echo "saved bench/${NAME}.json"
