#!/bin/bash

# Sanity test script for dnscrypt-proxy Docker container
# Tests that the container accepts DNS traffic and responds correctly

set -euo pipefail

# Configuration
IMAGE_NAME="dnscrypt-proxy-test"
CONTAINER_NAME="dnscrypt-proxy-test-container"
TEST_PORT="15353"  # Use non-standard port to avoid conflicts
TIMEOUT=30
TEST_DOMAIN="example.com"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

cleanup() {
    log "Cleaning up test environment..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    docker rmi "$IMAGE_NAME" 2>/dev/null || true
}

# Set up cleanup trap
trap cleanup EXIT

main() {
    log "Starting dnscrypt-proxy container sanity test..."
    
    # Check if dig is available
    if ! command -v dig &> /dev/null; then
        error "dig command not found. Please install dnsutils (apt install dnsutils) or bind-utils (yum install bind-utils)"
        exit 1
    fi
    
    # Check if we should build or use existing image
    if [[ "${USE_EXISTING_IMAGE:-}" == "true" ]]; then
        log "Using existing image: $IMAGE_NAME"
        # Check if image exists
        if ! docker images | grep -q "$IMAGE_NAME"; then
            error "Image $IMAGE_NAME not found. Cannot use existing image."
            exit 1
        fi
    else
        # Build the Docker image
        log "Building Docker image..."
        if ! docker build -t "$IMAGE_NAME" .; then
            error "Failed to build Docker image"
            error "This may be due to network restrictions preventing access to package repositories."
            error "In CI environments, set USE_EXISTING_IMAGE=true to test a pre-built image."
            exit 1
        fi
    fi
    
    # Start the container
    log "Starting dnscrypt-proxy container on port $TEST_PORT..."
    if ! docker run -d --name "$CONTAINER_NAME" -p "$TEST_PORT:53/udp" "$IMAGE_NAME"; then
        error "Failed to start container"
        exit 1
    fi
    
    # Wait for container to be ready
    log "Waiting for container to be ready..."
    sleep 5
    
    # Check if container is running
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        error "Container is not running"
        docker logs "$CONTAINER_NAME" || true
        exit 1
    fi
    
    # Wait a bit more for dnscrypt-proxy to initialize
    log "Waiting for dnscrypt-proxy to initialize..."
    sleep 10
    
    # Test DNS resolution
    log "Testing DNS resolution for $TEST_DOMAIN..."
    if dig @127.0.0.1 -p "$TEST_PORT" +time=5 +tries=2 "$TEST_DOMAIN" A | grep -q "ANSWER SECTION"; then
        log "✓ DNS query successful - container accepts traffic and returns responses"
    else
        error "DNS query failed - container may not be accepting traffic properly"
        log "Container logs:"
        docker logs "$CONTAINER_NAME" || true
        exit 1
    fi
    
    # Test with a second domain to ensure consistency
    log "Testing DNS resolution for google.com..."
    if dig @127.0.0.1 -p "$TEST_PORT" +time=5 +tries=2 google.com A | grep -q "ANSWER SECTION"; then
        log "✓ Second DNS query successful"
    else
        warn "Second DNS query failed, but first one worked"
    fi
    
    # Verify container health
    log "Checking container health status..."
    sleep 5  # Give time for health check to run
    health_status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    if [[ "$health_status" == "healthy" ]]; then
        log "✓ Container health check passed"
    elif [[ "$health_status" == "starting" ]]; then
        warn "Container health check still starting"
    else
        warn "Container health check status: $health_status"
    fi
    
    log "All tests passed! Container successfully accepts DNS traffic."
}

# Run main function
main "$@"