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

# Delete build configuration
echo "Removing build configuration..."
delete_resource buildconfig $AGENT_NAME

# Delete image stream
echo "Removing image stream..."
delete_resource imagestream $AGENT_NAME

# Delete agent entry 
echo "Removing image stream..."
delete_resource agent $AGENT_NAME

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
