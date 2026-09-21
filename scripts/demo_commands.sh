#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
INVOICE_PATH="${1:-sample_invoices/invoice_001.png}"

echo "1) Upload invoice"
curl -sS -X POST -F "file=@${INVOICE_PATH}" "${BASE_URL}/documents"

echo
echo "2) Open ${BASE_URL}/docs and use the returned document ID for extraction/review/export."
