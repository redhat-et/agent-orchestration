#!/bin/bash
set -euo pipefail

# Load local environment overrides if present
if [ -f "./env" ]; then
  set -a
  . ./env
  set +a
fi

# Check if AGENT_NAME is provided
if [ -z "${1:-}" ]; then
    echo "Usage: $0 <AGENT_NAME> [CONFIG_FILE]"
    echo "Example: $0 device-status ./configs/device-status.yaml"
    exit 1
fi

AGENT_NAME="$1"
shift || true

# Backward-compatible optional positional CONFIG_FILE
CONFIG_FILE=""
if [ $# -gt 0 ] && [[ "${1:-}" != -* ]]; then
  CONFIG_FILE="$1"
  shift || true
fi

# Optional flags
JWKS_URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --jwks-url)
      JWKS_URL="${2:-}"
      shift 2 || true
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

echo "Deploying $AGENT_NAME A2A Agent to OpenShift..."

# Check if logged into OpenShift
if ! oc whoami &>/dev/null; then
    echo "Error: Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

echo "Current project: $(oc project -q)"

# Python picker (simple & robust: venv -> python3 -> python)
if [ -x "../venv/bin/python" ]; then
  PYBIN="../venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYBIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYBIN="$(command -v python)"
else
  echo "Error: Python not found (need ../venv/bin/python, python3, or python)." >&2
  exit 1
fi

# Create build configuration if it doesn't exist
echo "Setting up build configuration..."
if ! oc get buildconfig $AGENT_NAME &>/dev/null; then
    echo "   Creating new build configuration..."
    oc new-build --strategy docker --binary --name $AGENT_NAME
else
    echo "   Build configuration already exists."
fi

# Build the container image
echo "Building container image..."
oc start-build $AGENT_NAME --from-dir=. --follow

# Prepare secrets and config
echo "Preparing secrets and config..."

# Optional: signing secret. Detect from common locations or env var
# Prefer repo tokens directory if present
JWK_PATH_DEFAULT="../tokens/jwk_private.json"
JWK_PATH="${A2A_SIGNING_JWK_PATH:-}"
if [ -z "${JWK_PATH}" ] && [ -f "$JWK_PATH_DEFAULT" ]; then
  JWK_PATH="$JWK_PATH_DEFAULT"
fi
if [ -n "${JWK_PATH}" ] && [ -f "$JWK_PATH" ]; then
  echo "   Creating/updating signing secret from $JWK_PATH"
  oc create secret generic ${AGENT_NAME}-a2a-signing --from-file=jwk_private.json="$JWK_PATH" -o yaml --dry-run=client | oc apply -f -
else
  echo "   No signing key found; generating a new RSA keypair and creating secret"
  TMPDIR=$(mktemp -d)
  export AGENT_NAME TMPDIR
  if [ -n "$PYBIN" ]; then
    # Try Python+Authlib JWK generation first
    if "$PYBIN" - <<'PY' >/dev/null 2>&1; then
from authlib.jose.rfc7517.jwk import JsonWebKey
PY
      "$PYBIN" - <<'PY' > "$TMPDIR/jwk_private.json"
from authlib.jose.rfc7517.jwk import JsonWebKey
import json, os
kid = f"{os.environ.get('A2A_SIGNING_KID','agent')}-key"
key = JsonWebKey.generate_key("RSA", 2048, options={"kid": kid, "use": "sig", "alg": "RS256"}, is_private=True)
print(json.dumps(key.as_dict(is_private=True)))
PY
    else
      # Fallback: use openssl to make PEM; if conversion lib isn't available locally,
      # store PEM directly as the secret. The agent can import PEM at runtime.
      echo "   Authlib not available in $PYBIN; using openssl fallback"
      openssl genrsa -out "$TMPDIR/private.pem" 2048 >/dev/null 2>&1
      if [ -f "$TMPDIR/private.pem" ]; then
        if "$PYBIN" - <<'PY' >/dev/null 2>&1; then
from authlib.jose.rfc7517.jwk import JsonWebKey
PY
          "$PYBIN" - <<'PY' > "$TMPDIR/jwk_private.json"
from authlib.jose.rfc7517.jwk import JsonWebKey
import json, os
pem = open(os.path.join(os.environ['TMPDIR'],'private.pem'),'r').read()
kid = f"{os.environ.get('A2A_SIGNING_KID','agent')}-key"
key = JsonWebKey.import_key(pem, options={"kid": kid, "use": "sig", "alg": "RS256"})
print(json.dumps(key.as_dict(is_private=True)))
PY
        else
          echo "   Authlib still not available for conversion; storing PEM in secret (agent will import PEM)."
          cp "$TMPDIR/private.pem" "$TMPDIR/jwk_private.json"
        fi
      else
        echo "Error: openssl failed to create private key." >&2
        rm -rf "$TMPDIR"
        exit 1
      fi
    fi
  else
    echo "Error: No suitable Python interpreter found to generate JWK." >&2
    rm -rf "$TMPDIR"
    exit 1
  fi
  oc create secret generic ${AGENT_NAME}-a2a-signing --from-file=jwk_private.json="$TMPDIR/jwk_private.json" -o yaml --dry-run=client | oc apply -f -
  rm -rf "$TMPDIR"
fi

# Register agent's public key with central JWKS server
echo "Registering public key with central JWKS server..."
PROJECT=$(oc project -q)

# Extract public key from the agent's signing secret (robust: handles JWK JSON or PEM)
PUBLIC_KEY=$("$PYBIN" - "$AGENT_NAME" "$PROJECT" <<'PY'
import sys, json, base64, subprocess

name = sys.argv[1]
ns = sys.argv[2]

def load_secret(secret_name: str, namespace: str) -> dict:
    res = subprocess.run(
        ["oc", "get", "secret", f"{secret_name}-a2a-signing", "-n", namespace, "-o", "json"],
        capture_output=True, text=True, check=True
    )
    return json.loads(res.stdout)

try:
    secret = load_secret(name, ns)
    data_b64 = (secret.get("data") or {}).get("jwk_private.json")
    if not data_b64:
        raise RuntimeError("secret data key 'jwk_private.json' not found")

    raw_bytes = base64.b64decode(data_b64)
    raw_text = raw_bytes.decode("utf-8", errors="ignore").strip()

    public_jwk = None
    # Try JSON JWK first
    try:
        private_jwk = json.loads(raw_text)
        if isinstance(private_jwk, dict) and private_jwk.get("n") and private_jwk.get("e"):
            public_jwk = {
                "kty": private_jwk.get("kty", "RSA"),
                "n": private_jwk["n"],
                "e": private_jwk["e"],
            }
            for field in ("kid", "use", "alg"):
                if field in private_jwk:
                    public_jwk[field] = private_jwk[field]
    except Exception:
        public_jwk = None

    # If not JSON JWK, try PEM → JWK using authlib if available
    if public_jwk is None:
        try:
            from authlib.jose.rfc7517.jwk import JsonWebKey
            key = JsonWebKey.import_key(raw_text, options={"use": "sig"})
            public_jwk = key.as_dict(is_private=False)
        except Exception as e:
            raise RuntimeError(f"unable to derive public key from secret: {e}")

    print(json.dumps(public_jwk))
except Exception as e:
    print(f"Error extracting public key: {e}", file=sys.stderr)
    sys.exit(1)
PY
)

if [ -z "$PUBLIC_KEY" ]; then
    echo "   Warning: Could not extract public key. JWKS not updated."
else
    # Get existing JWKS or create new one
    EXISTING_JWKS=$(oc get configmap a2a-central-jwks -n "$PROJECT" -o jsonpath='{.data.jwks\.json}' 2>/dev/null || echo '{"keys":[]}')

    # Merge the new public key into JWKS (replace if kid matches, append otherwise)
    UPDATED_JWKS=$("$PYBIN" - "$EXISTING_JWKS" "$PUBLIC_KEY" <<'PY'
import sys, json

try:
    existing_jwks = json.loads(sys.argv[1])
    new_key = json.loads(sys.argv[2])

    # Ensure keys array exists
    if "keys" not in existing_jwks:
        existing_jwks["keys"] = []

    # Find and replace existing key with same kid, or append
    kid = new_key.get("kid")
    replaced = False
    if kid:
        for i, key in enumerate(existing_jwks["keys"]):
            if key.get("kid") == kid:
                existing_jwks["keys"][i] = new_key
                replaced = True
                break

    if not replaced:
        existing_jwks["keys"].append(new_key)

    print(json.dumps(existing_jwks))
except Exception as e:
    print(f"Error merging JWKS: {e}", file=sys.stderr)
    sys.exit(1)
PY
)

    if [ -n "$UPDATED_JWKS" ]; then
        # Update the ConfigMap
        echo "$UPDATED_JWKS" | oc create configmap a2a-central-jwks --from-file=jwks.json=/dev/stdin -n "$PROJECT" --dry-run=client -o yaml | oc apply -f -

        # Restart JWKS server if it exists
        if oc get deployment jwks-server -n "$PROJECT" >/dev/null 2>&1; then
            echo "   Restarting JWKS server to load new key..."
            oc rollout restart deployment/jwks-server -n "$PROJECT" >/dev/null 2>&1 || true
        else
            echo "   Warning: JWKS server deployment not found. Run setup_central_jwks.sh to create it."
        fi
        echo "   Public key registered successfully!"
    else
        echo "   Warning: Could not merge JWKS. Manual update may be required."
    fi
fi

# Create/update agent ConfigMap
CM_ARGS=(--from-literal=A2A_SIGN_CARD=true)
if [ -n "$JWKS_URL" ]; then
  CM_ARGS+=(--from-literal=A2A_JWKS_URL="$JWKS_URL")
  CM_ARGS+=(--from-literal=A2A_PUBLISH_JWKS=false)
  CM_ARGS+=(--from-literal=A2A_FAIL_IF_NO_SIGNING_KEY=true)
else
  CM_ARGS+=(--from-literal=A2A_PUBLISH_JWKS=true)
fi
oc create configmap ${AGENT_NAME}-config "${CM_ARGS[@]}" -o yaml --dry-run=client | oc apply -f -

# Apply the deployment configuration
echo "Applying deployment configuration..."
AGENT_NAME=$AGENT_NAME CONFIG_ARG="${CONFIG_FILE}" KB_FILE="${KB_FILE:-./data/default}" NAMESPACE="$(oc project -q)" envsubst < deployment.yaml | oc apply -f -

# Get the route hostname
echo "Getting route information..."
ROUTE_HOST=""
for i in {1..30}; do
    ROUTE_HOST=$(oc get route $AGENT_NAME -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
    if [ -n "$ROUTE_HOST" ]; then
        break
    fi
    echo "   Waiting for route to be created... (attempt $i/30)"
    sleep 2
done

if [ -z "$ROUTE_HOST" ]; then
    echo "Error: Could not get route host after 60 seconds."
    exit 1
fi

echo "   Route host: $ROUTE_HOST"

# Update deployment with route hostname
echo "Configuring agent with route URL..."
oc set env deployment/$AGENT_NAME OPENSHIFT_ROUTE_HOST="$ROUTE_HOST" AGENT_NAME="$AGENT_NAME"

# Fix image reference to use internal registry
echo "Updating image reference..."
PROJECT=$(oc project -q)
oc set image deployment/$AGENT_NAME $AGENT_NAME="image-registry.openshift-image-registry.svc:5000/$PROJECT/$AGENT_NAME:latest"

# Wait for deployment to complete
echo "Waiting for deployment to complete..."
oc rollout status deployment/$AGENT_NAME --timeout=300s

# Verify deployment
echo "Verifying deployment..."
POD_STATUS=$(oc get pods -l app=$AGENT_NAME -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")
if [ "$POD_STATUS" = "Running" ]; then
    echo "   Pod is running successfully!"
else
    echo "   Pod status: $POD_STATUS"
    echo "   Check logs with: oc logs -l app=$AGENT_NAME"
fi

# Test the agent card endpoint
echo "Testing agent card endpoint..."
AGENT_URL="https://$ROUTE_HOST/.well-known/agent.json"
if curl -k -s --max-time 10 "$AGENT_URL" >/dev/null 2>&1; then
    echo "   Agent card is accessible!"
else
    echo "   Agent card endpoint not yet ready. It may take a few more seconds."
fi

echo ""
echo "Deployment complete!"
echo "   Agent URL: https://$ROUTE_HOST"
echo "   Agent Card: https://$ROUTE_HOST/.well-known/agent.json"
echo ""
echo "Discovery labels added:"
echo "   ai.openshift.io/agent.class=a2a"
echo "   ai.openshift.io/agent.name=$AGENT_NAME"
echo "   a2a.agent=true"
echo "   a2a.agent.name=$AGENT_NAME"
echo "   a2a.agent.version=0.1.0"
echo ""
echo "Useful commands:"
echo "   View logs: oc logs -l app=$AGENT_NAME -f"
echo "   Check status: oc get pods -l app=$AGENT_NAME"
echo "   Test agent: curl -k https://$ROUTE_HOST/.well-known/agent.json"
