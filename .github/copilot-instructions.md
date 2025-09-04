# dnscrypt-proxy Docker Container

This repository packages the dnscrypt-proxy DNS resolver in a Docker container with custom configuration optimized for container deployment. It is NOT the main dnscrypt-proxy source code - it's a Docker wrapper that downloads and builds the official dnscrypt-proxy from GitHub.

**Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Prerequisites
- Docker must be installed and running
- Internet connectivity required for building (downloads Go source code and Alpine packages)
- Network access to GitHub and Alpine package repositories

### Build the Docker Image
**CRITICAL**: Docker builds take 3-5 minutes under normal conditions. **NEVER CANCEL** builds - set timeouts to 10+ minutes.

```bash
# Build the Docker image
docker build -t dnscrypt-proxy .
```

**Expected build time**: 3-5 minutes for initial build, 1-2 minutes with layer caching.

### Build with Multi-Platform Support (GitHub Actions style)
```bash
# Set up Docker buildx for multi-platform builds
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t nathanhowell/dnscrypt-proxy .
```

**Expected build time**: 8-12 minutes for multi-platform build. **NEVER CANCEL** - set timeout to 20+ minutes.

### Run the Container
```bash
# Run in foreground for testing
docker run --rm -p 53:53/udp dnscrypt-proxy

# Run as daemon
docker run -d --name dnscrypt-proxy --restart unless-stopped -p 53:53/udp dnscrypt-proxy

# Run with custom config
docker run -d --name dnscrypt-proxy --restart unless-stopped \
  -p 53:53/udp \
  -v /path/to/custom/dnscrypt-proxy.toml:/etc/dnscrypt-proxy/dnscrypt-proxy.toml \
  dnscrypt-proxy
```

## Build Troubleshooting

### Network Restrictions
If you encounter "Permission denied" or network timeout errors during build:
```
ERROR: unable to select packages: bind-tools (no such package): required by: world[bind-tools]
```

This indicates network restrictions preventing access to Alpine package repositories. The build process requires:
- Access to `dl-cdn.alpinelinux.org` for Alpine packages
- Access to `github.com` for downloading dnscrypt-proxy source
- Access to Go module proxy for dependencies

**In restricted environments**: Document that Docker builds will fail due to firewall limitations.

## Configuration

### Key Configuration Differences from Default
The included `dnscrypt-proxy.toml` differs from the upstream default in these ways:
- `listen_addresses = ['0.0.0.0:53']` - Listens on all interfaces (container-friendly)
- `user_name = 'nobody'` - Runs as unprivileged user
- `ipv6_servers = true` - Enables IPv6 DNS servers

### Modifying Configuration
1. Edit `dnscrypt-proxy.toml` for custom settings
2. Important sections:
   - **[Global]**: Basic server settings, listen addresses
   - **[sources]**: DNS resolver source lists (public-resolvers, relays)
   - **[query_log]**: Logging configuration
   - **[blocked_names]** and **[allowed_names]**: DNS filtering

3. Rebuild the Docker image after configuration changes:
```bash
docker build -t dnscrypt-proxy .
```

## Validation and Testing

### Automated Test Suite
The repository uses a comprehensive pytest-based test suite with Python 3.13 and uv for package management:

**Prerequisites:**
- Python 3.13 or later
- uv package manager
- Docker (for running containers)

**Running Tests:**
```bash
# Install dependencies with uv
uv sync

# Test any image (built or pre-built)
uv run python run_tests.py nathanhowell/dnscrypt-proxy:latest

# Build and test locally
uv run python run_tests.py --build

# Verbose test output
uv run python run_tests.py --verbose
```

**Test Structure:**
- **Critical Infrastructure Tests** (`@pytest.mark.critical`): Container startup, port binding, configuration loading
- **Network-Dependent Tests** (`@pytest.mark.network`): DNS resolution, upstream connections
- **Intelligent Exit Codes**:
  - Exit 0: All tests passed (container fully functional)
  - Exit 1: Critical infrastructure failure (real container problems that fail CI)
  - Exit 2: Network-dependent tests failed (expected in restricted environments, warns but passes CI)

### Manual Testing Steps
**CRITICAL**: Always test DNS functionality after making changes:

1. **Start the container**:
```bash
docker run --rm -p 53:53/udp dnscrypt-proxy
```

2. **Test DNS resolution** (from another terminal):
```bash
# Test basic DNS resolution
dig @127.0.0.1 example.com

# Test with specific record types
dig @127.0.0.1 MX example.com
dig @127.0.0.1 AAAA example.com

# Test DNSSEC validation
dig @127.0.0.1 +dnssec example.com
```

3. **Verify container health**:
```bash
# Check container logs
docker logs <container_id>

# Test the built-in healthcheck
docker inspect --format='{{.State.Health.Status}}' <container_id>
```

4. **Expected validation results**:
   - DNS queries should return valid responses
   - No error messages in container logs
   - Healthcheck should show "healthy" status

### Container Debugging
```bash
# Get shell access to running container
docker exec -it <container_id> sh

# Check dnscrypt-proxy status
docker exec -it <container_id> ps aux | grep dnscrypt-proxy

# View configuration
docker exec -it <container_id> cat /etc/dnscrypt-proxy/dnscrypt-proxy.toml
```

## GitHub Actions Workflow

### Automated Builds
The repository uses `.github/workflows/docker.yaml` for automated building:
- **Triggers**: Push to master, PR creation, releases
- **Platforms**: linux/amd64, linux/arm64
- **Registry**: Docker Hub (nathanhowell/dnscrypt-proxy)

### Build Process
1. Checks out repository
2. Sets up Docker buildx for multi-platform builds
3. Builds Docker image with layer caching
4. Pushes to Docker Hub (on non-PR events)

**Expected GitHub Actions build time**: 8-15 minutes. **NEVER CANCEL** - workflows need sufficient time.

## Common Tasks

### Repository Structure
```
.
├── .github/
│   ├── workflows/
│   │   └── docker.yaml          # Automated Docker build pipeline
│   └── dependabot.yml          # Dependency updates
├── Dockerfile                  # Multi-stage Docker build
├── dnscrypt-proxy.toml        # Custom dnscrypt-proxy configuration
└── README.md                  # Basic usage documentation
```

### Dockerfile Analysis
The Dockerfile uses a two-stage build:
1. **Build stage** (`golang:1-alpine3.22`):
   - Downloads dnscrypt-proxy 2.1.13 source from GitHub
   - Compiles with `go install -ldflags "-s -w"`
   - Produces static binary at `/go/bin/dnscrypt-proxy`

2. **Runtime stage** (`alpine:3.22`):
   - Installs `bind-tools` for healthcheck
   - Copies binary and configuration
   - Runs as unprivileged user with custom config

### Version Updates
To update dnscrypt-proxy version:
1. Edit `Dockerfile` line 5 to change version number
2. Update the tar.gz URL and directory path accordingly
3. Test build and functionality
4. Commit changes

## Development Workflow

### Making Changes
1. **Always test locally first**:
```bash
# Build and test with the automated test suite  
uv run python run_tests.py --build

# Or manually test the container
docker build -t dnscrypt-proxy-test .
docker run --rm -p 53:53/udp dnscrypt-proxy-test
```

2. **Run the comprehensive test suite** to validate all functionality:
```bash
uv run python run_tests.py --verbose
```

3. **Check container logs** for errors or warnings

4. **For configuration changes**: Compare with upstream example configuration to ensure compatibility

### Test Development
When adding new tests:
1. Add tests to `tests/test_dnscrypt_proxy.py` 
2. Use `@pytest.mark.critical` for infrastructure tests that must pass
3. Use `@pytest.mark.network` for tests that may fail in restricted network environments
4. Update `conftest.py` if new test fixtures are needed

### Release Process
1. Changes pushed to master trigger automated Docker Hub builds
2. GitHub releases create tagged versions  
3. Multi-platform images are built and pushed automatically

**Note**: This repository uses comprehensive pytest-based functional testing of the Docker container and DNS resolution, with intelligent CI feedback that distinguishes between critical infrastructure failures and expected network restrictions.