#!/usr/bin/env bash
set -euo pipefail

# Setup Central JWKS Server
#
# This script deploys a central JWKS server in OpenShift to serve public keys
# for A2A agent signature verification. The server is deployed with security
# best practices including TLS termination and health checks.
#
# Usage: ./setup_central_jwks.sh [/abs/path/to/jwks.json] [namespace] [--merge]
#
# Arguments:
#   jwks.json    - Path to JWKS file containing public keys (RFC 7517 format)
#                  Optional: if not provided, creates/updates with empty JWKS
#   namespace    - OpenShift namespace (optional, defaults to current project)
#   --merge      - Merge keys from file with existing JWKS instead of replacing

# Parse arguments
JWKS_FILE=""
NS=""
MERGE_MODE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --merge)
      MERGE_MODE=true
      shift
      ;;
    *)
      if [ -z "$JWKS_FILE" ]; then
        JWKS_FILE="$1"
      elif [ -z "$NS" ]; then
        NS="$1"
      else
        echo "Error: Unknown argument: $1" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

# Set defaults
NS="${NS:-$(oc project -q 2>/dev/null || true)}"
oc whoami >/dev/null 2>&1 || { echo "Error: not logged in (run 'oc login')." >&2; exit 1; }
[ -n "${NS}" ] || { echo "Error: no namespace (pass as arg or 'oc project')." >&2; exit 1; }

# If JWKS file provided, validate it
if [ -n "${JWKS_FILE}" ]; then
  [ -f "${JWKS_FILE}" ] || { echo "Error: file not found: ${JWKS_FILE}" >&2; exit 1; }

  # Validate JWKS is JSON with a 'keys' array (RFC 7517)
  if ! command -v jq >/dev/null; then
    echo "Warning: jq not found; skipping strict JWKS validation."
  else
    jq -e '.keys and (.keys | type=="array")' "${JWKS_FILE}" >/dev/null \
      || { echo "Error: JWKS must contain a 'keys' array." >&2; exit 1; }
  fi
fi

# Find Python interpreter
if [ -x "../venv/bin/python" ]; then
  PYBIN="../venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYBIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYBIN="$(command -v python)"
else
  PYBIN=""
fi

# Handle JWKS ConfigMap creation/update
if [ "$MERGE_MODE" = true ] && [ -n "$JWKS_FILE" ] && [ -n "$PYBIN" ]; then
  echo "Merging JWKS from ${JWKS_FILE} with existing ConfigMap..."

  # Get existing JWKS or create empty one
  EXISTING_JWKS=$(oc -n "${NS}" get configmap a2a-central-jwks -o jsonpath='{.data.jwks\.json}' 2>/dev/null || echo '{"keys":[]}')
  NEW_JWKS=$(cat "${JWKS_FILE}")

  # Merge JWKs (replace keys with matching kid, append new ones)
  MERGED_JWKS=$("$PYBIN" - <<'PY'
import sys, json

try:
    existing = json.loads(sys.argv[1])
    new = json.loads(sys.argv[2])

    if "keys" not in existing:
        existing["keys"] = []
    if "keys" not in new:
        print(json.dumps(existing))
        sys.exit(0)

    # Build a dict of existing keys by kid
    existing_by_kid = {}
    for i, key in enumerate(existing["keys"]):
        kid = key.get("kid")
        if kid:
            existing_by_kid[kid] = i

    # Merge new keys
    for new_key in new["keys"]:
        kid = new_key.get("kid")
        if kid and kid in existing_by_kid:
            # Replace existing key
            existing["keys"][existing_by_kid[kid]] = new_key
        else:
            # Append new key
            existing["keys"].append(new_key)

    print(json.dumps(existing))
except Exception as e:
    print(f"Error merging JWKS: {e}", file=sys.stderr)
    sys.exit(1)
PY
"$EXISTING_JWKS" "$NEW_JWKS")

  echo "$MERGED_JWKS" | oc -n "${NS}" create configmap a2a-central-jwks \
    --from-file=jwks.json=/dev/stdin --dry-run=client -o yaml | oc -n "${NS}" apply -f -
elif [ -n "$JWKS_FILE" ]; then
  echo "Applying ConfigMap a2a-central-jwks from ${JWKS_FILE}..."
  oc -n "${NS}" create configmap a2a-central-jwks \
    --from-file=jwks.json="${JWKS_FILE}" --dry-run=client -o yaml | oc -n "${NS}" apply -f -
else
  echo "Creating/updating ConfigMap a2a-central-jwks with empty JWKS..."
  echo '{"keys":[]}' | oc -n "${NS}" create configmap a2a-central-jwks \
    --from-file=jwks.json=/dev/stdin --dry-run=client -o yaml | oc -n "${NS}" apply -f -
fi

# Apply Deployment, Service, and Route declaratively
cat <<'YAML' | oc -n "${NS}" apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jwks-server
  labels: { app: jwks-server }
spec:
  replicas: 1
  selector: { matchLabels: { app: jwks-server } }
  template:
    metadata:
      labels: { app: jwks-server }
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: nginx
          # Using specific version for reproducibility (consider pinning by digest in production)
          image: nginxinc/nginx-unprivileged:1.27-alpine
          ports: [{ containerPort: 8080, name: http }]
          env:
            - name: NGINX_WORKER_PROCESSES
              value: "2"
          volumeMounts:
            - name: jwks-vol
              mountPath: /usr/share/nginx/html/.well-known
              readOnly: true
          readinessProbe:
            httpGet: { path: /.well-known/jwks.json, port: http }
            initialDelaySeconds: 2
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          livenessProbe:
            httpGet: { path: /.well-known/jwks.json, port: http }
            initialDelaySeconds: 15
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          resources:
            requests: { cpu: "10m", memory: "64Mi" }
            limits:   { cpu: "100m", memory: "128Mi" }
      volumes:
        - name: jwks-vol
          configMap:
            name: a2a-central-jwks
---
apiVersion: v1
kind: Service
metadata:
  name: jwks-server
  labels: { app: jwks-server }
spec:
  selector: { app: jwks-server }
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: jwks-server
  labels: { app: jwks-server }
spec:
  to: { kind: Service, name: jwks-server }
  port: { targetPort: http }
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
YAML

echo "Waiting for rollout..."
oc -n "${NS}" rollout status deploy/jwks-server --timeout=180s

HOST="$(oc -n "${NS}" get route jwks-server -o jsonpath='{.spec.host}')"
URL="https://${HOST}/.well-known/jwks.json"

echo "Validating JWKS endpoint at ${URL}..."
for i in {1..60}; do
  if BODY="$(curl -fsS --max-time 3 "${URL}" 2>/dev/null)" && \
     echo "${BODY}" | jq -e '.keys and (.keys | type=="array")' >/dev/null 2>&1; then
    echo "${URL}"
    exit 0
  fi
  sleep 1
done
echo "Error: JWKS endpoint validation failed after 60 seconds." >&2
exit 1
