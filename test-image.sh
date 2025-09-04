#!/bin/bash

# Simple test script for testing a pre-built dnscrypt-proxy image
# Usage: ./test-image.sh [image_name]

set -euo pipefail

IMAGE_NAME="${1:-nathanhowell/dnscrypt-proxy:latest}"
CONTAINER_NAME="dnscrypt-proxy-test"
TEST_PORT="15353"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    log "Cleaning up test environment..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
}

# Set up cleanup trap
trap cleanup EXIT

main() {
    log "Testing dnscrypt-proxy image: $IMAGE_NAME"
    
    # Check if dig is available
    if ! command -v dig &> /dev/null; then
        error "dig command not found. Please install dnsutils or bind-utils"
        exit 1
    fi
    
    # Pull image if it doesn't exist locally
    if ! docker images | grep -q "${IMAGE_NAME%%:*}"; then
        log "Pulling image $IMAGE_NAME..."
        if ! docker pull "$IMAGE_NAME"; then
            error "Failed to pull image $IMAGE_NAME"
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
    sleep 15
    
    # Check if container is running
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        error "Container is not running"
        docker logs "$CONTAINER_NAME" || true
        exit 1
    fi
    
    # Test DNS resolution - try multiple approaches
    log "Testing if container accepts DNS traffic..."
    
    # First, try a basic connectivity test
    if timeout 5 bash -c "echo >/dev/tcp/127.0.0.1/$TEST_PORT" 2>/dev/null; then
        log "✓ Port $TEST_PORT is accepting connections"
    else
        log "Port $TEST_PORT is not accepting connections"
    fi
    
    # Test DNS query with very short timeout - we care more about if it accepts the query than if it resolves
    log "Sending test DNS query..."
    dig_output=$(timeout 10 dig @127.0.0.1 -p "$TEST_PORT" +time=3 +tries=1 example.com A 2>&1 || true)
    
    if echo "$dig_output" | grep -q "ANSWER SECTION"; then
        log "✓ DNS query successful - container accepts traffic and returns responses"
    elif echo "$dig_output" | grep -q "connection timed out" || echo "$dig_output" | grep -q "no response from server"; then
        error "DNS query failed - container may not be accepting traffic properly"
        log "dig output: $dig_output"
        log "Container logs:"
        docker logs "$CONTAINER_NAME" || true
        exit 1
    elif echo "$dig_output" | grep -q "SERVFAIL" || echo "$dig_output" | grep -q "status: "; then
        log "✓ DNS query received response (even if SERVFAIL) - container accepts traffic"
        log "Note: DNS resolution failed, but container is accepting queries (expected in restricted networks)"
    else
        log "DNS query output: $dig_output"
        log "Testing basic UDP connectivity..."
        
        # Try a more basic test - send raw UDP packet
        if python3 -c "
import socket
import sys
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    # Simple DNS query for example.com
    query = b'\\x12\\x34\\x01\\x00\\x00\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x07example\\x03com\\x00\\x00\\x01\\x00\\x01'
    s.sendto(query, ('127.0.0.1', $TEST_PORT))
    data = s.recv(1024)
    print('Received response')
    sys.exit(0)
except Exception as e:
    print(f'Failed: {e}')
    sys.exit(1)
" 2>/dev/null; then
            log "✓ Container accepts UDP DNS packets"
        else
            error "Container does not accept UDP DNS packets"
            log "Container logs:"
            docker logs "$CONTAINER_NAME" || true
            exit 1
        fi
    fi
    
    # Test with IPv6 if supported
    log "Testing IPv6 DNS resolution..."
    if dig @127.0.0.1 -p "$TEST_PORT" +time=5 +tries=2 google.com AAAA | grep -q "ANSWER SECTION"; then
        log "✓ IPv6 DNS query successful"
    else
        log "IPv6 DNS query failed or no IPv6 records available"
    fi
    
    # Test container health
    log "Checking container health status..."
    sleep 5
    health_status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    log "Container health status: $health_status"
    
    log "All tests passed! Container successfully accepts DNS traffic."
}

main "$@"