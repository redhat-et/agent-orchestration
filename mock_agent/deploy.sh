#!/bin/bash
set -eu

# Check if AGENT_NAME is provided
if [ -z "${1:-}" ]; then
    echo "Usage: $0 <AGENT_NAME>"
    echo "Example: $0 device-status"
    exit 1
fi

AGENT_NAME="$1"

echo "Deploying $AGENT_NAME A2A Agent to OpenShift..."

# Check if logged into OpenShift
if ! oc whoami &>/dev/null; then
    echo "Error: Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

echo "Current project: $(oc project -q)"

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

# Apply the deployment configuration
echo "Applying deployment configuration..."
AGENT_NAME=$AGENT_NAME KB_FILE="${KB_FILE:-./data/default}" envsubst < deployment.yaml | oc apply -f -

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
echo ""
echo "Useful commands:"
echo "   View logs: oc logs -l app=$AGENT_NAME -f"
echo "   Check status: oc get pods -l app=$AGENT_NAME"
echo "   Test agent: curl -k https://$ROUTE_HOST/.well-known/agent.json"
