#!/bin/bash
# Create the file crawl configuration for the sample files and run the crawl.
#
# Everything goes through Fess's own HTTP interface, so it works against any
# running stack (including one on non-default ports):
#   1. sign in to the admin console with the form login and make sure an
#      access token with the admin-api permission exists (the Admin API accepts
#      tokens only, never the console session);
#   2. create the file crawl config for file:///data/files/ through the Admin API
#      (an existing config of the same name is reused);
#   3. start the Default Crawler job and wait until the documents are indexed.
#
# Safe to run again: it re-uses the token and the crawl config and simply
# crawls again (unchanged files are skipped by the incremental crawl).
#
#   bash bin/configure.sh               # configure and crawl
#   bash bin/configure.sh --smb         # also crawl the same files over SMB
#                                       # (start the Samba service first:
#                                       #  docker compose --profile smb up -d)
#   CRAWL_TIMEOUT=900 bash bin/configure.sh
set -euo pipefail

WITH_SMB=false
for arg in "$@"; do
  case "${arg}" in
    --smb) WITH_SMB=true ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "Unknown option: ${arg} (see --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f ./.env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

BASE="http://localhost:${FESS_HTTP_PORT:-8080}"
ADMIN_USER="${FESS_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${FESS_ADMIN_PASSWORD:-admin}"
TOKEN_NAME="${FESS_TOKEN_NAME:-filesearch-dev}"
CONFIG_NAME="${FESS_CRAWL_CONFIG_NAME:-Sample Files}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
CRAWL_TIMEOUT="${CRAWL_TIMEOUT:-600}"

COOKIES="$(mktemp)"
trap 'rm -f "${COOKIES}"' EXIT

log() { printf '[configure] %s\n' "$*"; }
die() { printf '[configure] ERROR: %s\n' "$*" >&2; exit 1; }

# jget '<python expression over d>' reads JSON on stdin.
jget() { python3 -c 'import json,sys; d=json.load(sys.stdin); print('"$1"')'; }

# ---------------------------------------------------------------------------
# 1. Wait for Fess
# ---------------------------------------------------------------------------
log "Waiting for ${BASE}/api/v2/health (up to ${HEALTH_TIMEOUT}s)..."
deadline=$((SECONDS + HEALTH_TIMEOUT))
healthy() {
  curl -sf -m 5 "${BASE}/api/v2/health" 2>/dev/null \
    | jget 'd["response"]["status"] == 0 and d["response"]["engine"]["status"] in ("GREEN", "YELLOW")' 2>/dev/null
}
until [ "$(healthy || true)" = "True" ]; do
  [ "${SECONDS}" -lt "${deadline}" ] || die "Fess did not become healthy. Check: docker compose logs fess01"
  sleep 3
done
log "Fess is healthy."

# ---------------------------------------------------------------------------
# 2. Admin console session and access token
# ---------------------------------------------------------------------------
form_token() { sed -n 's/.*name="lastaflute.action.TRANSACTION_TOKEN" value="\([^"]*\)".*/\1/p' | head -1; }

page="$(curl -sf -m 30 -c "${COOKIES}" -b "${COOKIES}" "${BASE}/login/")"
tt="$(printf '%s' "${page}" | form_token)"
[ -n "${tt}" ] || die "Could not read the login form token from ${BASE}/login/."
curl -s -m 30 -o /dev/null -c "${COOKIES}" -b "${COOKIES}" \
  --data-urlencode "lastaflute.action.TRANSACTION_TOKEN=${tt}" \
  --data-urlencode "username=${ADMIN_USER}" --data-urlencode "password=${ADMIN_PASSWORD}" \
  --data-urlencode "login=Login" "${BASE}/login/"
landing="$(curl -s -m 30 -o /dev/null -w '%{redirect_url}' -b "${COOKIES}" "${BASE}/admin/")"
case "${landing}" in
  */admin/dashboard/*) ;;
  *) die "Admin login failed for user '${ADMIN_USER}' (landing page: '${landing}'). Set FESS_ADMIN_USER / FESS_ADMIN_PASSWORD." ;;
esac
log "Signed in to the admin console as ${ADMIN_USER}."

# Print the id of the access token named TOKEN_NAME (empty if none).
find_token_id() {
  curl -sf -m 30 -b "${COOKIES}" "${BASE}/admin/accesstoken/" | NAME="${TOKEN_NAME}" python3 -c '
import os, re, sys
html = sys.stdin.read()
m = re.search(r"data-href=\"/admin/accesstoken/details/4/([^\"]+)\"[^>]*>\s*<td>" + re.escape(os.environ["NAME"]) + r"</td>", html)
print(m.group(1) if m else "")'
}

token_id="$(find_token_id)"
if [ -z "${token_id}" ]; then
  log "Creating access token '${TOKEN_NAME}' (permission {role}admin-api)..."
  page="$(curl -sf -m 30 -b "${COOKIES}" -c "${COOKIES}" "${BASE}/admin/accesstoken/createnew/")"
  tt="$(printf '%s' "${page}" | form_token)"
  created_time="$(printf '%s' "${page}" | sed -n 's/.*name="createdTime" value="\([^"]*\)".*/\1/p' | head -1)"
  curl -s -m 30 -o /dev/null -b "${COOKIES}" -c "${COOKIES}" \
    --data-urlencode "lastaflute.action.TRANSACTION_TOKEN=${tt}" \
    --data-urlencode "crudMode=1" --data-urlencode "createdBy=${ADMIN_USER}" --data-urlencode "createdTime=${created_time}" \
    --data-urlencode "name=${TOKEN_NAME}" --data-urlencode "permissions={role}admin-api" \
    --data-urlencode "parameterName=" --data-urlencode "expires=" --data-urlencode "create=Create" \
    "${BASE}/admin/accesstoken/create"
  token_id="$(find_token_id)"
  [ -n "${token_id}" ] || die "The access token was not created."
fi
TOKEN="$(curl -sf -m 30 -b "${COOKIES}" "${BASE}/admin/accesstoken/details/4/${token_id}" \
         | tr '\n' ' ' | sed -n 's/.*<th>Token<\/th>[[:space:]]*<td>\([^<]*\)<\/td>.*/\1/p')"
[ -n "${TOKEN}" ] || die "Could not read the access token value."

api() { curl -s -m 60 -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' "$@"; }

status="$(api "${BASE}/api/admin/fileconfig/settings" | jget 'd["response"]["status"]')"
[ "${status}" = "0" ] || die "The Admin API rejected the access token (status ${status})."
log "Admin API access token '${TOKEN_NAME}' is ready."

# ---------------------------------------------------------------------------
# 3. File crawl configuration
# ---------------------------------------------------------------------------
# ensure_file_config <name> <paths> <sort order>: print the id of the config
# with that name, creating it when it does not exist yet.
ensure_file_config() {
  local name="$1" paths="$2" sort_order="$3" id body resp
  id="$(api "${BASE}/api/admin/fileconfig/settings?size=100" | NAME="${name}" python3 -c '
import json, os, sys
d = json.load(sys.stdin)["response"]["settings"]
print(next((s["id"] for s in d if s["name"] == os.environ["NAME"]), ""))')"
  if [ -n "${id}" ]; then
    log "File crawl config '${name}' already exists (${id}); reusing it." >&2
  else
    # The Admin API takes snake_case field names (num_of_thread, not numOfThread).
    # "{role}guest" makes the documents visible to anonymous users.
    body="$(NAME="${name}" PATHS="${paths}" SORT_ORDER="${sort_order}" python3 -c '
import json, os
print(json.dumps({
    "name": os.environ["NAME"],
    "description": "Sample file tree (see bin/generate_sample.py)",
    "paths": os.environ["PATHS"],
    "num_of_thread": 3,
    "interval_time": 0,
    "boost": 1.0,
    "available": "true",
    "sort_order": int(os.environ["SORT_ORDER"]),
    "permissions": "{role}guest",
}))')"
    resp="$(api -X POST "${BASE}/api/admin/fileconfig/setting" -d "${body}")"
    [ "$(printf '%s' "${resp}" | jget 'd["response"]["status"]')" = "0" ] || die "Creating the crawl config '${name}' failed: ${resp}"
    id="$(printf '%s' "${resp}" | jget 'd["response"]["id"]')"
    log "Created file crawl config '${name}' (${id}) for ${paths}" >&2
  fi
  printf '%s' "${id}"
}

ensure_file_config "${CONFIG_NAME}" "file:///data/files/" 0 >/dev/null
expected="$(find ./data/files -type f 2>/dev/null | wc -l | tr -d ' ')"

if [ "${WITH_SMB}" = "true" ]; then
  docker compose --profile smb ps --status running --services 2>/dev/null | grep -qx samba01 \
    || die "The samba01 service is not running. Start it with: docker compose --profile smb up -d"
  smb_id="$(ensure_file_config "${CONFIG_NAME} (SMB)" "smb://samba01/share/" 1)"
  have_auth="$(api "${BASE}/api/admin/fileauth/settings?size=100" | ID="${smb_id}" python3 -c '
import json, os, sys
d = json.load(sys.stdin)["response"]["settings"]
print(any(s.get("file_config_id") == os.environ["ID"] for s in d))')"
  if [ "${have_auth}" = "True" ]; then
    log "File authentication for samba01 already exists; reusing it."
  else
    # Port 0 means "the default port". A port such as 445 would only match
    # smb://samba01:445/..., never smb://samba01/share/.
    body="$(ID="${smb_id}" python3 -c '
import json, os
print(json.dumps({"hostname": "samba01", "port": 0, "protocol_scheme": "SAMBA", "username": "filesearch",
                  "password": "filesearch", "file_config_id": os.environ["ID"]}))')"
    resp="$(api -X POST "${BASE}/api/admin/fileauth/setting" -d "${body}")"
    [ "$(printf '%s' "${resp}" | jget 'd["response"]["status"]')" = "0" ] || die "Creating the file authentication failed: ${resp}"
    log "Created file authentication for samba01 (user filesearch)."
  fi
  expected=$((expected * 2))
fi

# ---------------------------------------------------------------------------
# 4. Crawl and wait for the index
# ---------------------------------------------------------------------------
job_running() { api "${BASE}/api/admin/scheduler/setting/default_crawler" | jget 'd["response"]["setting"]["running"]'; }
doc_count() { curl -s -m 30 "${BASE}/api/v2/search?q=*&num=1" | jget 'd["response"].get("record_count", 0)' 2>/dev/null || echo 0; }

if [ "$(job_running)" = "True" ]; then
  log "The Default Crawler is already running; waiting for it."
else
  resp="$(api -X PUT "${BASE}/api/admin/scheduler/default_crawler/start")"
  [ "$(printf '%s' "${resp}" | jget 'd["response"]["status"]')" = "0" ] || die "Starting the Default Crawler failed: ${resp}"
  log "Started the Default Crawler."
  sleep 3
fi

log "Waiting for the crawl to finish (up to ${CRAWL_TIMEOUT}s; expecting ${expected} documents)..."
deadline=$((SECONDS + CRAWL_TIMEOUT))
last=-1
stable=0
while :; do
  count="$(doc_count)"
  running="$(job_running)"
  printf '[configure]   indexed=%s crawler_running=%s\n' "${count}" "${running}"
  if [ "${running}" = "False" ] && [ "${count}" -gt 0 ]; then
    if [ "${count}" = "${last}" ]; then stable=$((stable + 1)); else stable=0; fi
    [ "${stable}" -ge 1 ] && break
  fi
  last="${count}"
  [ "${SECONDS}" -lt "${deadline}" ] || die "Timed out after ${CRAWL_TIMEOUT}s with ${count} documents. See data/fess/var/log/fess/fess-crawler.log"
  sleep 5
done

log "Indexed ${count} documents (expected ${expected})."
if [ "${count}" -lt "${expected}" ]; then
  log "WARNING: $((expected - count)) documents were not indexed. Check Admin > Crawler > Failure URL and data/fess/var/log/fess/fess-crawler.log."
fi
log "Search UI:  ${BASE}/"
log "Admin:      ${BASE}/admin/  (${ADMIN_USER} / ${ADMIN_PASSWORD})"
log "Access token for /api/admin/* (local development only): ${TOKEN}"
log "PDF / Office thumbnails appear after the Thumbnail Generator job runs (every minute)."
