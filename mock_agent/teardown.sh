#!/bin/bash
set -e

# Check if AGENT_NAME is provided
if [ -z "${1:-}" ]; then
    echo "Usage: $0 <AGENT_NAME>"
    echo "Example: $0 device-status"
    exit 1
fi

AGENT_NAME="$1"

echo "Tearing down $AGENT_NAME A2A Agent from OpenShift..."

# Check if logged into OpenShift
if ! oc whoami &>/dev/null; then
    echo "Error: Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

echo "Current project: $(oc project -q)"

# Function to safely delete resource
delete_resource() {
    local resource_type=$1
    local resource_name=$2

    if oc get "$resource_type" "$resource_name" &>/dev/null; then
        echo "   Deleting $resource_type/$resource_name..."
        oc delete "$resource_type" "$resource_name"
    else
        echo "   $resource_type/$resource_name not found (already deleted)"
    fi
}

# Delete Agent CR if present
echo "Removing Agent custom resource..."
delete_resource agent $AGENT_NAME || true

# Delete route
echo "Removing route..."
delete_resource route $AGENT_NAME

# Delete service
echo "Removing service..."
delete_resource service $AGENT_NAME-service

# Delete deployment
echo "Removing deployment..."
delete_resource deployment $AGENT_NAME

# Wait for pods to terminate
echo "Waiting for pods to terminate..."
for i in {1..30}; do
    POD_COUNT=$(oc get pods -l app=$AGENT_NAME --no-headers 2>/dev/null | wc -l || echo "0")
    if [ "$POD_COUNT" -eq 0 ]; then
        echo "   All pods terminated."
        break
    fi
    echo "   Waiting for $POD_COUNT pod(s) to terminate... (attempt $i/30)"
    sleep 2
done

# Delete configmap created by deploy
echo "Removing configmap..."
delete_resource configmap ${AGENT_NAME}-config

# Delete signing secret
echo "Removing signing secret..."
delete_resource secret ${AGENT_NAME}-a2a-signing

# Delete build configuration
echo "Removing build configuration..."
delete_resource buildconfig $AGENT_NAME

# Delete image stream
echo "Removing image stream..."
delete_resource imagestream $AGENT_NAME

# Optionally remove central JWKS entry (ConfigMap) key for this agent (safe merge)
if [ "${REMOVE_CENTRAL_JWKS:-false}" = "true" ]; then
  echo "Removing agent key from central JWKS ConfigMap (a2a-central-jwks)..."
  if oc get configmap a2a-central-jwks &>/dev/null; then
    EXISTING_JWKS=$(oc get configmap a2a-central-jwks -o jsonpath='{.data.jwks\.json}' 2>/dev/null || echo '{"keys":[]}')
    UPDATED_JWKS=$(python3 - <<'PY'
import sys, json, os
existing = json.loads(os.environ.get('EXISTING_JWKS','{"keys":[]}'))
kid_prefix = os.environ.get('AGENT_NAME','agent')
existing['keys'] = [k for k in existing.get('keys', []) if k.get('kid','').split('-')[0] != kid_prefix]
print(json.dumps(existing))
PY
)
    if [ -n "$UPDATED_JWKS" ]; then
      echo "$UPDATED_JWKS" | oc create configmap a2a-central-jwks --from-file=jwks.json=/dev/stdin --dry-run=client -o yaml | oc apply -f -
      if oc get deployment jwks-server >/dev/null 2>&1; then
        oc rollout restart deployment/jwks-server >/dev/null 2>&1 || true
      fi
      echo "   Central JWKS updated."
    fi
  else
    echo "   Central JWKS ConfigMap not found; skipping."
  fi
fi

# Clean up any remaining builds
echo "Cleaning up builds..."
BUILDS=$(oc get builds -l build=$AGENT_NAME -o name 2>/dev/null || echo "")
if [ -n "$BUILDS" ]; then
    echo "   Deleting builds..."
    echo "$BUILDS" | xargs -r oc delete
else
    echo "   No builds to clean up."
fi

# Verify cleanup
echo "Verifying cleanup..."
REMAINING_RESOURCES=$(oc get all -l app=$AGENT_NAME -o name 2>/dev/null || echo "")
if [ -n "$REMAINING_RESOURCES" ]; then
    echo "   Some resources may still exist:"
    echo "$REMAINING_RESOURCES"
    echo "   You may need to delete them manually."
else
    echo "   All resources have been removed."
fi

echo ""
echo "Teardown complete!"
echo "   All $AGENT_NAME resources have been removed from OpenShift."
echo ""
echo "To redeploy:"
echo "   ./deploy.sh $AGENT_NAME"
