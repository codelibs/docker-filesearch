#!/bin/sh
# Idempotent OpenSearch ML Commons embedding-model setup for the file hybrid search.
# Runs in the init-semantic container (an Alpine image; it installs curl + jq). Writes the
# deployed model id to ${MODEL_ID_FILE} for the Fess entrypoint wrapper to inject as a JVM -D.
#
# Fess (15.8+) generates embeddings itself by calling
# _plugins/_ml/models/<id>/_predict -- from the Content Chunk Vector Indexer job for
# the document chunks and at search time for the query -- so a deployed model is all
# OpenSearch has to provide. There is no ingest pipeline and no stored search
# pipeline: Fess 15.9 sends the hybrid query with an inline pipeline per request.
#
# Re-running is safe: an existing model group / model is reused rather than recreated,
# so restarts are fast and never register duplicate models.
set -eu

OPENSEARCH_URL="${OPENSEARCH_URL:-http://search01:9200}"
MODEL_NAME="${MODEL_NAME:-huggingface/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2}"
MODEL_VERSION="${MODEL_VERSION:-1.0.1}"
MODEL_FORMAT="${MODEL_FORMAT:-TORCH_SCRIPT}"
MODEL_DIMENSION="${MODEL_DIMENSION:-384}"
MODEL_ID_FILE="${MODEL_ID_FILE:-/semantic/model_id}"
# Seconds to wait for ONE ML task: registering (the download) and deploying each get this long.
MAX_WAIT="${MAX_WAIT:-900}"

# Log to stderr so messages survive command substitution and stay visible in
# `docker compose logs init-semantic` (stdout is captured by callers like wait_task).
log() { echo "[setup-semantic] $*" >&2; }

# curl and jq come from the Alpine package index. Without network access (a `docker compose
# down` / `up` offline) there is nothing to register: reuse the id the last run wrote when
# OpenSearch still has that model DEPLOYED. Busybox wget and grep are enough to check that.
if ! apk add --no-cache curl jq >/dev/null; then
  log "WARN: could not install curl and jq (no network?); looking for the model of the last run."
  last_id="$(cat "${MODEL_ID_FILE}" 2>/dev/null || true)"
  last_doc=""
  [ -z "${last_id}" ] || last_doc="$(wget -qO- "${OPENSEARCH_URL}/_plugins/_ml/models/${last_id}" 2>/dev/null || true)"
  if [ -n "${last_doc}" ] && printf '%s' "${last_doc}" | grep -qF "\"name\":\"${MODEL_NAME}\"" \
      && printf '%s' "${last_doc}" | grep -qF '"model_state":"DEPLOYED"' \
      && printf '%s' "${last_doc}" | grep -qF "\"embedding_dimension\":${MODEL_DIMENSION}"; then
    log "Reusing the deployed model ${last_id} from ${MODEL_ID_FILE}."
    exit 0
  fi
  log "ERROR: no deployed ${MODEL_NAME} (${MODEL_DIMENSION} dimensions) from an earlier run to reuse; connect to the network and run again."
  exit 1
fi

# os METHOD PATH [BODY] -> echoes response body
os() {
  if [ -n "${3:-}" ]; then
    curl -fsS -X "$1" -H 'Content-Type: application/json' "${OPENSEARCH_URL}$2" -d "$3"
  else
    curl -fsS -X "$1" "${OPENSEARCH_URL}$2"
  fi
}

# wait_task TASK_ID [JQ_FIELD] -> waits for COMPLETED, optionally echoes a field
wait_task() {
  _waited=0
  while :; do
    # `|| true` so a transient non-2xx (the cluster is busy downloading/deploying the
    # model in this window) does not abort the script under `set -e`; we just retry.
    _resp="$(os GET "/_plugins/_ml/tasks/$1" || true)"
    _state="$(echo "${_resp}" | jq -r '.state // empty')"
    case "${_state}" in
      COMPLETED) [ -n "${2:-}" ] && echo "${_resp}" | jq -r ".$2 // empty"; return 0 ;;
      FAILED|COMPLETED_WITH_ERROR|CANCELLED)
        log "ERROR: task $1 ${_state}: $(echo "${_resp}" | jq -rc '.error // empty')"; return 1 ;;
    esac
    _waited=$((_waited + 3))
    [ "${_waited}" -ge "${MAX_WAIT}" ] && { log "ERROR: task $1 timed out after ${MAX_WAIT}s"; return 1; }
    sleep 3
  done
}

log "Waiting for OpenSearch at ${OPENSEARCH_URL}..."
i=0
until curl -fsS "${OPENSEARCH_URL}/_cluster/health" >/dev/null 2>&1; do
  i=$((i + 1))
  [ "${i}" -ge 150 ] && { log "ERROR: OpenSearch is not reachable"; exit 1; }
  sleep 2
done

# Allow models to run on non-dedicated ML nodes too (defensive; node already has ml role).
os PUT /_cluster/settings '{"persistent":{"plugins.ml_commons.only_run_on_ml_node":false}}' >/dev/null || true

# Model group: reuse by exact name, else register.
# Capture search response separately so `|| true` applies only to the os call, not jq.
_grp_resp="$(os POST /_plugins/_ml/model_groups/_search \
  "{\"size\":20,\"query\":{\"match\":{\"name\":\"${MODEL_NAME}\"}}}" || true)"
group_id="$(echo "${_grp_resp}" | jq -r --arg n "${MODEL_NAME}" '[.hits.hits[] | select(._source.name==$n)][0]._id // empty')"
if [ -z "${group_id}" ]; then
  log "Registering model group..."
  group_id="$(os POST /_plugins/_ml/model_groups/_register \
    "{\"name\":\"${MODEL_NAME}\",\"description\":\"Embedding model for Fess semantic search.\"}" \
    | jq -r '.model_group_id // empty')"
fi
[ -n "${group_id}" ] || { log "ERROR: could not determine model_group_id"; exit 1; }
log "model_group_id=${group_id}"

# Model: reuse an existing registered model in the group, else register a new one.
# Capture search response separately so `|| true` applies only to the os call, not jq.
_mdl_resp="$(os POST /_plugins/_ml/models/_search \
  "{\"size\":20,\"query\":{\"bool\":{\"must\":[{\"match\":{\"name\":\"${MODEL_NAME}\"}},{\"term\":{\"model_group_id\":\"${group_id}\"}}]}}}" || true)"
# Reuse a model in any state that is not broken, the most deployed first; ignore REGISTERING
# and DEPLOY_FAILED so a broken leftover does not permanently wedge the stack. UNDEPLOYED and
# DEPLOYING happen after a restart; registering again there would download ~490 MB twice.
model_id="$(echo "${_mdl_resp}" | jq -r --arg n "${MODEL_NAME}" \
  '[.hits.hits[] | select(._source.name==$n)] as $m
   | (["DEPLOYED","PARTIALLY_DEPLOYED","REGISTERED","UNDEPLOYED","DEPLOYING"] | map(. as $s | $m[] | select(._source.model_state==$s)))[0]._id // empty')"
if [ -z "${model_id}" ]; then
  log "Registering model ${MODEL_NAME} v${MODEL_VERSION} (OpenSearch downloads it; may take several minutes)..."
  task_id="$(os POST /_plugins/_ml/models/_register \
    "{\"name\":\"${MODEL_NAME}\",\"version\":\"${MODEL_VERSION}\",\"model_format\":\"${MODEL_FORMAT}\",\"model_group_id\":\"${group_id}\"}" \
    | jq -r '.task_id // empty')"
  [ -n "${task_id}" ] || { log "ERROR: model registration did not return a task_id"; exit 1; }
  model_id="$(wait_task "${task_id}" model_id)"
fi
[ -n "${model_id}" ] || { log "ERROR: could not determine model_id"; exit 1; }
log "model_id=${model_id}"

# Deploy if not already DEPLOYED (a deploy that is already running is waited for first).
state="$(os GET "/_plugins/_ml/models/${model_id}" | jq -r '.model_state // empty')"
waited=0
while [ "${state}" = "DEPLOYING" ]; do
  [ "${waited}" -lt "${MAX_WAIT}" ] || { log "ERROR: model is still DEPLOYING after ${MAX_WAIT}s"; exit 1; }
  sleep 3
  waited=$((waited + 3))
  state="$(os GET "/_plugins/_ml/models/${model_id}" | jq -r '.model_state // empty')"
done
if [ "${state}" != "DEPLOYED" ]; then
  log "Deploying model (state=${state:-unknown})..."
  dtask="$(os POST "/_plugins/_ml/models/${model_id}/_deploy" | jq -r '.task_id // empty')"
  [ -n "${dtask}" ] && wait_task "${dtask}" >/dev/null || true
  state="$(os GET "/_plugins/_ml/models/${model_id}" | jq -r '.model_state // empty')"
fi
[ "${state}" = "DEPLOYED" ] || { log "ERROR: model is not DEPLOYED (state=${state:-unknown})"; exit 1; }

# Validate the embedding dimension matches the configured index mapping dimension.
# Fetch the model document once; a real failure aborts here under set -e rather than
# silently leaving actual_dim empty and skipping the validation.
model_doc="$(os GET "/_plugins/_ml/models/${model_id}")"
actual_dim="$(echo "${model_doc}" | jq -r '.model_config.embedding_dimension // empty')"
if [ -n "${actual_dim}" ] && [ "${actual_dim}" != "${MODEL_DIMENSION}" ]; then
  log "ERROR: model embedding_dimension=${actual_dim} != MODEL_DIMENSION=${MODEL_DIMENSION}. Update MODEL_DIMENSION to match."
  exit 1
fi

# Hand off the model id to the Fess entrypoint wrapper.
mkdir -p "$(dirname "${MODEL_ID_FILE}")"
printf '%s' "${model_id}" > "${MODEL_ID_FILE}"
log "Wrote model_id to ${MODEL_ID_FILE}. Semantic setup complete."
