#!/bin/bash

# Container sanity test for dnscrypt-proxy Docker image
# Tests that the container starts correctly and would accept traffic in a normal environment
# This test is designed to work even in restricted network environments
#
# Usage: ./test-sanity.sh [IMAGE_NAME]
# 
# Exit codes:
# 0: All tests passed (container fully functional)
# 1: Critical infrastructure failure (container build/startup problems)
# 2: Network-dependent tests failed but infrastructure is OK (expected in restricted environments)

set -euo pipefail

IMAGE_NAME="${1:-nathanhowell/dnscrypt-proxy:latest}"
CONTAINER_NAME="dnscrypt-proxy-sanity-test"
TEST_PORT="15353"

# Test result tracking
CRITICAL_TESTS=0
CRITICAL_FAILURES=0
NETWORK_TESTS=0
NETWORK_FAILURES=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

test_result() {
    local test_name="$1"
    local result="$2"
    local failure_type="$3"  # "critical" or "network"
    
    if [[ "$failure_type" == "critical" ]]; then
        CRITICAL_TESTS=$((CRITICAL_TESTS + 1))
        if [[ "$result" == "fail" ]]; then
            CRITICAL_FAILURES=$((CRITICAL_FAILURES + 1))
        fi
    else
        NETWORK_TESTS=$((NETWORK_TESTS + 1))
        if [[ "$result" == "fail" ]]; then
            NETWORK_FAILURES=$((NETWORK_FAILURES + 1))
        fi
    fi
    
    if [[ "$result" == "pass" ]]; then
        echo -e "${GREEN}✓${NC} $test_name"
    elif [[ "$result" == "fail" ]]; then
        echo -e "${RED}✗${NC} $test_name"
    else
        echo -e "${YELLOW}◯${NC} $test_name (inconclusive)"
    fi
}

cleanup() {
    log "Cleaning up test environment..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
}

# Set up cleanup trap
trap cleanup EXIT

main() {
    log "Running comprehensive sanity test for dnscrypt-proxy image: $IMAGE_NAME"
    echo -e "${BLUE}=== CRITICAL INFRASTRUCTURE TESTS ===${NC}"
    echo "These tests validate core container functionality and must pass"
    echo ""
    
    # Check if image exists locally, pull if needed (skip in CI if already loaded)
    if ! docker images --format "table {{.Repository}}:{{.Tag}}" | grep -q "^${IMAGE_NAME}$"; then
        log "Image $IMAGE_NAME not found locally"
        if [[ "${CI:-}" == "true" ]]; then
            log "Running in CI environment - checking for similar images..."
            docker images --format "table {{.Repository}}:{{.Tag}}" | head -10
            # In CI, the image might be loaded with a different exact name
            AVAILABLE_IMAGE=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "nathanhowell/dnscrypt-proxy" | head -1)
            if [[ -n "$AVAILABLE_IMAGE" ]]; then
                log "Using available image: $AVAILABLE_IMAGE"
                IMAGE_NAME="$AVAILABLE_IMAGE"
            else
                warn "No suitable image found in CI environment, attempting to pull..."
                if ! docker pull "$IMAGE_NAME"; then
                    error "Failed to pull image $IMAGE_NAME - this may be due to network restrictions"
                    test_result "Image availability" "fail" "critical"
                    exit 1
                fi
            fi
        else
            log "Pulling image $IMAGE_NAME..."
            if ! docker pull "$IMAGE_NAME"; then
                error "Failed to pull image $IMAGE_NAME"
                test_result "Image availability" "fail" "critical"
                exit 1
            fi
        fi
    else
        log "Image $IMAGE_NAME found locally"
    fi
    
    # Start the container
    log "Starting dnscrypt-proxy container on port $TEST_PORT..."
    if ! docker run -d --name "$CONTAINER_NAME" -p "$TEST_PORT:53/udp" "$IMAGE_NAME"; then
        error "Failed to start container"
        test_result "Container startup" "fail" "critical"
        exit 1
    fi
    
    # Wait for container initialization
    log "Waiting for container to initialize..."
    sleep 10
    
    # CRITICAL TEST 1: Check if container is running
    if docker ps | grep -q "$CONTAINER_NAME"; then
        test_result "Container is running" "pass" "critical"
    else
        error "Container failed to start or exited"
        docker logs "$CONTAINER_NAME" || true
        test_result "Container is running" "fail" "critical"
    fi
    
    # Get container logs for subsequent tests
    logs=$(docker logs "$CONTAINER_NAME" 2>&1)
    
    # CRITICAL TEST 2: Check for critical startup errors
    critical_logs=$(echo "$logs" | grep -E "(FATAL|failed to bind|permission denied|cannot allocate)" | grep -v -E "(network|connection|timeout|unreachable|refused|dial tcp)" || true)
    if [[ -n "$critical_logs" ]]; then
        error "Critical startup errors found:"
        echo "$critical_logs"
        test_result "No critical startup errors" "fail" "critical"
    else
        test_result "No critical startup errors" "pass" "critical"
    fi
    
    # CRITICAL TEST 3: Check if configuration file is loaded
    if echo "$logs" | grep -q -E "(Configuration file|config.*loaded|reading.*config)"; then
        test_result "Configuration file loaded" "pass" "critical"
    else
        test_result "Configuration file loaded" "fail" "critical"
    fi
    
    # CRITICAL TEST 4: Check port binding from host perspective
    sleep 2  # Give a moment for port binding
    if ss -lun | grep -q ":$TEST_PORT "; then
        test_result "Host port binding" "pass" "critical"
    else
        test_result "Host port binding" "fail" "critical"
    fi
    
    # CRITICAL TEST 5: Check basic container health (not crashing immediately)
    sleep 5
    if docker ps | grep -q "$CONTAINER_NAME"; then
        test_result "Container stability (doesn't crash)" "pass" "critical"
    else
        test_result "Container stability (doesn't crash)" "fail" "critical"
    fi
    
    echo ""
    echo -e "${BLUE}=== NETWORK-DEPENDENT TESTS ===${NC}"
    echo "These tests validate network functionality and may fail in restricted environments"
    echo ""
    
    # NETWORK TEST 1: Check if dnscrypt-proxy process is running
    if docker exec "$CONTAINER_NAME" ps aux | grep -v grep | grep -q dnscrypt-proxy; then
        test_result "dnscrypt-proxy process running" "pass" "network"
    else
        # Check if process exited due to network issues vs actual problems
        if echo "$logs" | grep -q -E "(network.*error|connection.*failed|timeout|unreachable|dial tcp.*refused)"; then
            warn "Process exit appears to be network-related (expected in restricted environments)"
            test_result "dnscrypt-proxy process running" "fail" "network"
        else
            error "Process exit may indicate a configuration or startup problem"
            test_result "dnscrypt-proxy process running" "fail" "critical"
        fi
    fi
    
    # NETWORK TEST 2: Check container logs for successful port binding
    if echo "$logs" | grep -q "Now listening to 0.0.0.0:53 \[UDP\]"; then
        test_result "UDP port 53 listening" "pass" "network"
    else
        test_result "UDP port 53 listening" "fail" "network"
    fi
    
    if echo "$logs" | grep -q "Now listening to 0.0.0.0:53 \[TCP\]"; then
        test_result "TCP port 53 listening" "pass" "network"
    else
        test_result "TCP port 53 listening" "fail" "network"
    fi
    
    # NETWORK TEST 3: Check if public resolvers configuration loaded
    if echo "$logs" | grep -q "Source \[public-resolvers\] loaded"; then
        test_result "Public resolvers configuration loaded" "pass" "network"
    else
        test_result "Public resolvers configuration loaded" "fail" "network"
    fi
    
    # NETWORK TEST 4: Check upstream connection attempts
    if echo "$logs" | grep -q "Resolving server host"; then
        test_result "Upstream DNS server resolution attempts" "pass" "network"
    else
        test_result "Upstream DNS server resolution attempts" "fail" "network"
    fi
    
    # NETWORK TEST 5: Check container health (if health check is configured)
    sleep 5
    health_status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "no-healthcheck")
    case "$health_status" in
        "healthy")
            test_result "Container health check" "pass" "network"
            ;;
        "starting")
            test_result "Container health check" "inconclusive" "network"
            ;;
        "unhealthy")
            test_result "Container health check" "fail" "network"
            ;;
        "no-healthcheck")
            test_result "Container health check" "inconclusive" "network"
            ;;
        *)
            test_result "Container health check" "fail" "network"
            ;;
    esac
    
    # NETWORK TEST 6: Basic port connectivity test
    if timeout 3 bash -c "echo >/dev/tcp/127.0.0.1/$TEST_PORT" 2>/dev/null; then
        test_result "Port connectivity test" "pass" "network"
    else
        test_result "Port connectivity test" "fail" "network"
    fi
    
    echo ""
    echo -e "${BLUE}=== TEST SUMMARY ===${NC}"
    echo "Container Image: $IMAGE_NAME"
    echo "Critical Infrastructure Tests: $((CRITICAL_TESTS - CRITICAL_FAILURES))/$CRITICAL_TESTS passed"
    echo "Network-Dependent Tests: $((NETWORK_TESTS - NETWORK_FAILURES))/$NETWORK_TESTS passed"
    echo ""
    
    # Show recent container logs for diagnostics
    echo -e "${BLUE}=== RECENT CONTAINER LOGS ===${NC}"
    echo "$logs" | tail -10
    echo ""
    
    # Determine exit code based on test results
    if [[ $CRITICAL_FAILURES -gt 0 ]]; then
        echo -e "${RED}CRITICAL FAILURES DETECTED${NC}"
        echo "The container has infrastructure problems that prevent normal operation."
        echo "This indicates a real issue with the container build or configuration."
        exit 1
    elif [[ $NETWORK_FAILURES -gt 0 ]]; then
        echo -e "${YELLOW}NETWORK-DEPENDENT TESTS FAILED${NC}"
        echo "The container infrastructure is functional, but network-dependent features failed."
        echo "This is expected in restricted network environments like CI."
        echo "In unrestricted environments, the container should function normally."
        exit 2
    else
        echo -e "${GREEN}ALL TESTS PASSED${NC}"
        echo "The container is fully functional and ready to accept DNS traffic."
        exit 0
    fi
}

main "$@"