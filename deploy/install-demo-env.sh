#!/usr/bin/env bash

# Baseline installer for kagent + OpenShift AI demo environment
# This script prepares any OpenShift cluster for the kagent+RHOAI integration demo

set -eu

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/manifests"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check oc CLI
    if ! command -v oc &> /dev/null; then
        log_error "oc CLI not found. Please install OpenShift CLI."
        exit 1
    fi

    # Check helm CLI
    if ! command -v helm &> /dev/null; then
        log_error "helm CLI not found. Please install Helm."
        exit 1
    fi

    # Check if logged into cluster
    if ! oc whoami &> /dev/null; then
        log_error "Not logged into OpenShift cluster. Run 'oc login' first."
        exit 1
    fi

    # Check OpenAI API key
    if [ -z "${OPENAI_API_KEY:-}" ]; then
        log_error "OPENAI_API_KEY environment variable not set."
        log_info "Export your OpenAI API key: export OPENAI_API_KEY=sk-..."
        exit 1
    fi

    log_info "Prerequisites check passed"
}

# Install kagent
install_kagent() {
    log_info "Installing kagent..."

    # Check if kagent is already installed
    if helm list -n kagent | grep -q kagent; then
        log_warn "kagent already installed, skipping..."
        return 0
    fi

    # Install CRDs
    log_info "Installing kagent CRDs..."
    helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
        --namespace kagent \
        --create-namespace \
        --wait

    # Install kagent
    log_info "Installing kagent core..."
    helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
        --namespace kagent \
        --set providers.openAI.apiKey=$OPENAI_API_KEY \
        --wait

    log_info "kagent installation complete"
}

# Install ServiceMesh operator
install_servicemesh_operator() {
    log_info "Installing ServiceMesh operator..."

    # Check if already installed
    if oc get subscription servicemeshoperator -n openshift-operators &> /dev/null; then
        log_warn "ServiceMesh operator already installed, skipping..."
        return 0
    fi

    # Create subscription
    log_info "Creating ServiceMesh operator subscription..."
    oc apply -f "${MANIFESTS_DIR}/servicemesh-operator.yaml"

    # Wait for CSV to be successful
    log_info "Waiting for ServiceMesh operator CSV to be ready (this may take a few minutes)..."
    timeout=600
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        csv_phase=$(oc get csv -n openshift-operators -l operators.coreos.com/servicemeshoperator.openshift-operators -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
        if [ "$csv_phase" == "Succeeded" ]; then
            log_info "CSV phase: Succeeded"
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    if [ $elapsed -ge $timeout ]; then
        log_error "ServiceMesh operator CSV installation timed out"
        exit 1
    fi

    log_info "ServiceMesh operator installation complete"
}

# Install Serverless operator
install_serverless_operator() {
    log_info "Installing Serverless operator..."

    # Check if already installed
    if oc get subscription serverless-operator -n openshift-serverless &> /dev/null; then
        log_warn "Serverless operator already installed, skipping..."
        return 0
    fi

    # Create subscription
    log_info "Creating Serverless operator subscription..."
    oc apply -f "${MANIFESTS_DIR}/serverless-operator.yaml"

    # Wait for CSV to be successful
    log_info "Waiting for Serverless operator CSV to be ready (this may take a few minutes)..."
    timeout=600
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        csv_phase=$(oc get csv -n openshift-serverless -l operators.coreos.com/serverless-operator.openshift-serverless -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
        if [ "$csv_phase" == "Succeeded" ]; then
            log_info "CSV phase: Succeeded"
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    if [ $elapsed -ge $timeout ]; then
        log_error "Serverless operator CSV installation timed out"
        exit 1
    fi

    log_info "Serverless operator installation complete"
}

# Install OpenShift AI operator
install_rhoai_operator() {
    log_info "Installing OpenShift AI operator..."

    # Check if operator namespace exists
    if oc get namespace redhat-ods-operator &> /dev/null; then
        log_warn "OpenShift AI operator namespace already exists, checking installation..."
        if oc get subscription rhods-operator -n redhat-ods-operator &> /dev/null; then
            log_warn "OpenShift AI operator already installed, skipping..."
            return 0
        fi
    fi

    # Create operator namespace and subscription
    log_info "Creating OpenShift AI operator subscription..."
    oc apply -f "${MANIFESTS_DIR}/rhoai-operator.yaml"

    # Wait for CSV to be successful
    log_info "Waiting for OpenShift AI operator CSV to be ready (this may take a few minutes)..."
    timeout=600
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        csv_phase=$(oc get csv -n redhat-ods-operator -l operators.coreos.com/rhods-operator.redhat-ods-operator -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
        if [ "$csv_phase" == "Succeeded" ]; then
            log_info "CSV phase: Succeeded"
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    if [ $elapsed -ge $timeout ]; then
        log_error "Operator CSV installation timed out"
        exit 1
    fi

    # Wait for deployment to be ready
    log_info "Waiting for operator deployment to be ready..."
    oc wait --for=condition=Available deployment/rhods-operator -n redhat-ods-operator --timeout=300s || {
        log_error "Operator deployment not ready"
        exit 1
    }

    log_info "OpenShift AI operator installation complete"
}

# Create DataScienceCluster
create_datasciencecluster() {
    log_info "Creating DataScienceCluster..."

    # Check if DSC already exists
    if oc get datasciencecluster default-dsc &> /dev/null; then
        log_warn "DataScienceCluster already exists, skipping..."
        return 0
    fi

    # Wait for CRD to be available
    log_info "Waiting for DataScienceCluster CRD to be available..."
    until oc get crd datascienceclusters.datasciencecluster.opendatahub.io &> /dev/null; do
        sleep 5
    done

    log_info "Creating DataScienceCluster with KServe enabled..."
    oc apply -f "${MANIFESTS_DIR}/datasciencecluster.yaml"

    log_info "DataScienceCluster creation initiated"
    log_warn "Note: Full deployment may take 5-10 minutes. Monitor with: oc get pods -n redhat-ods-applications"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."

    # Check kagent
    log_info "Checking kagent components..."
    if oc get deployment -n kagent kagent-controller &> /dev/null; then
        log_info "  kagent-controller deployed"
    else
        log_warn "  kagent-controller not found"
    fi

    # Check OpenShift AI operator
    log_info "Checking OpenShift AI operator..."
    if oc get deployment -n redhat-ods-operator rhods-operator &> /dev/null; then
        log_info "  rhods-operator deployed"
    else
        log_warn "  rhods-operator not found"
    fi

    # Check DataScienceCluster
    log_info "Checking DataScienceCluster..."
    if oc get datasciencecluster default-dsc &> /dev/null; then
        log_info "  DataScienceCluster created"
    else
        log_warn "  DataScienceCluster not found"
    fi

    log_info ""
    log_info "================================================"
    log_info "Installation Summary"
    log_info "================================================"
    log_info ""
    log_info "kagent:"
    log_info "  Namespace: kagent"
    log_info "  UI: oc get route kagent-ui -n kagent"
    log_info ""
    log_info "ServiceMesh:"
    log_info "  Namespace: openshift-operators"
    log_info ""
    log_info "Serverless:"
    log_info "  Namespace: openshift-serverless"
    log_info ""
    log_info "OpenShift AI:"
    log_info "  Operator Namespace: redhat-ods-operator"
    log_info "  Application Namespace: redhat-ods-applications"
    log_info "  Dashboard: Check routes in redhat-ods-applications"
    log_info ""
    log_info "Next Steps:"
    log_info "  1. Wait for all components to be ready:"
    log_info "     oc get pods -n kagent"
    log_info "     oc get pods -n redhat-ods-applications"
    log_info "     oc get datasciencecluster default-dsc -o jsonpath='{.status.conditions}' | jq '.[] | select(.type==\"KserveReady\")'"
    log_info "  2. Access kagent UI:"
    log_info "     oc get route kagent-ui -n kagent -o jsonpath='{.spec.host}'"
    log_info "  3. Deploy example agents from examples/ directory"
    log_info ""
}

# Main installation flow
main() {
    log_info "================================================"
    log_info "kagent + OpenShift AI Demo Environment Installer"
    log_info "================================================"
    log_info ""

    check_prerequisites
    install_kagent
    install_servicemesh_operator
    install_serverless_operator
    install_rhoai_operator
    create_datasciencecluster
    verify_installation

    log_info ""
    log_info "Installation complete"
}

main "$@"
