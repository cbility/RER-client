#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${RER_EMAIL:?Set RER_EMAIL in .env}"
: "${RER_PASSWORD:?Set RER_PASSWORD in .env}"
: "${SMARTSUITE_API_TOKEN:?Set SMARTSUITE_API_TOKEN in .env}"
: "${MAKE_API_KEY:?Set MAKE_API_KEY in .env}"
: "${SMARTSUITE_ACCOUNT_ID:?Set SMARTSUITE_ACCOUNT_ID in .env}"
: "${SMARTSUITE_TABLE_ID:?Set SMARTSUITE_TABLE_ID in .env}"
: "${SMARTSUITE_RECORD_ID:?Set SMARTSUITE_RECORD_ID in .env}"

environment_file="$(mktemp --suffix=.json)"
trap 'rm -f "$environment_file"' EXIT

python - "$environment_file" <<'PY'
import json
import os
import sys

environment = {
    "Variables": {
        "PLAYWRIGHT_HEADLESS": os.environ.get("PLAYWRIGHT_HEADLESS", "true"),
        "RER_MFA_MAX_RETRIES": os.environ.get("RER_MFA_MAX_RETRIES", "5"),
        "RER_MFA_WAIT_SECONDS": os.environ.get("RER_MFA_WAIT_SECONDS", "10"),
        "RER_EMAIL": os.environ["RER_EMAIL"],
        "RER_PASSWORD": os.environ["RER_PASSWORD"],
        "SMARTSUITE_API_URL": os.environ.get("SMARTSUITE_API_URL", "https://app.smartsuite.com/api/v1"),
        "SMARTSUITE_API_TOKEN": os.environ["SMARTSUITE_API_TOKEN"],
        "MAKE_API_KEY": os.environ["MAKE_API_KEY"],
        "SMARTSUITE_ACCOUNT_ID": os.environ["SMARTSUITE_ACCOUNT_ID"],
        "SMARTSUITE_TABLE_ID": os.environ["SMARTSUITE_TABLE_ID"],
        "SMARTSUITE_RECORD_ID": os.environ["SMARTSUITE_RECORD_ID"],
        "SMARTSUITE_COOKIES_FIELD": os.environ.get("SMARTSUITE_COOKIES_FIELD", "session_cookies"),
        "SMARTSUITE_REFRESHED_AT_FIELD": os.environ.get("SMARTSUITE_REFRESHED_AT_FIELD", ""),
        "SMARTSUITE_TIMEOUT_SECONDS": os.environ.get("SMARTSUITE_TIMEOUT_SECONDS", "30"),
    }
}

with open(sys.argv[1], "w", encoding="utf-8") as file:
    json.dump(environment, file)
PY

region="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-west-2}}"
function_name="$(aws cloudformation describe-stack-resource \
  --stack-name RER-client \
  --logical-resource-id RERSessionAuthFunction \
  --region "$region" \
  --query 'StackResourceDetail.PhysicalResourceId' \
  --output text)"

aws lambda update-function-configuration \
  --function-name "$function_name" \
  --environment "file://$environment_file" \
  --region "$region" \
  --no-cli-pager >/dev/null

aws lambda wait function-updated --function-name "$function_name" --region "$region"
printf 'Session-auth Lambda environment updated.\n'
