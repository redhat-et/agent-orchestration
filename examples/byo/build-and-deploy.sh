#!/usr/bin/env bash
set -eu

echo "Building and deploying BYO mock agent to kagent..."

# Check if logged into OpenShift
if ! oc whoami &>/dev/null; then
    echo "Error: Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

PROJECT="oc-dynamic-agents"
IMAGE_NAME="mock-agents"
FULL_IMAGE="image-registry.openshift-image-registry.svc:5000/${PROJECT}/${IMAGE_NAME}:latest"

echo "Current project: $(oc project -q)"
echo "Building image: ${FULL_IMAGE}"

# Create build configuration if it doesn't exist
echo "Setting up build configuration..."
if ! oc get buildconfig ${IMAGE_NAME} -n ${PROJECT} &>/dev/null; then
    echo "   Creating new build configuration in namespace ${PROJECT}..."
    oc new-build --strategy docker --binary --name ${IMAGE_NAME} -n ${PROJECT}
else
    echo "   Build configuration already exists."
fi

# Build the container image
echo "Building container image..."
oc start-build ${IMAGE_NAME} -n ${PROJECT} --from-dir=. --follow

echo ""
echo "✅ Image built: ${FULL_IMAGE}"
echo ""
echo "To deploy the agent:"
echo "   kubectl apply -f deploy.yaml"
echo ""
echo "To verify:"
echo "   kubectl get agents -n ${PROJECT}"
echo "   kubectl describe agent message-queue-monitor -n ${PROJECT}"
echo ""
echo "To test the agent card endpoint:"
echo "   kubectl port-forward -n kagent svc/kagent-controller 8083:8083"
echo "   curl http://localhost:8083/api/a2a/${PROJECT}/message-queue-monitor/.well-known/agent.json"
