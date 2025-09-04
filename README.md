# dnscrypt-proxy Docker image

This is a no-frills Docker image for [dnscrypt-proxy](https://github.com/DNSCrypt/dnscrypt-proxy).

## Quick Start

```bash
# Run the container
docker run -d --name dnscrypt-proxy --restart unless-stopped -p 53:53/udp nathanhowell/dnscrypt-proxy

# Test functionality
docker run --rm -p 53:53/udp nathanhowell/dnscrypt-proxy &
dig @127.0.0.1 example.com
```

## Testing

To test that the container starts correctly and accepts traffic, use the Python-based pytest test suite:

```bash
# Test a pre-built image from Docker Hub (recommended)
python test_container.py nathanhowell/dnscrypt-proxy:latest

# Build and test a local image
python test_container.py --build

# Alternative: use the compatibility wrapper scripts
./test-sanity.py nathanhowell/dnscrypt-proxy:latest
```

The test suite provides intelligent feedback with meaningful exit codes:
- **Exit 0**: All tests passed (container fully functional)
- **Exit 1**: Critical infrastructure failure (real container problems)
- **Exit 2**: Network-dependent tests failed (expected in restricted environments)

### Test Categories

**Critical Infrastructure Tests** (must pass):
- Container startup and stability
- Port binding and host connectivity
- Configuration file loading
- No critical startup errors

**Network-Dependent Tests** (may fail in restricted environments):
- dnscrypt-proxy process health
- DNS server resolution attempts
- Upstream connection establishment
- Health check status

### Requirements

Install test dependencies:
```bash
pip install -r requirements.txt
```

Required system packages:
- `docker` (for container management)
- `dig` command (usually in `dnsutils` or `bind-utils` package)

## Configuration

The configuration is lightly modified from the supplied [example-dnscrypt-proxy.toml](https://github.com/DNSCrypt/dnscrypt-proxy/blob/master/dnscrypt-proxy/example-dnscrypt-proxy.toml):

```diff
42c42
< listen_addresses = ['127.0.0.1:53']
---
> listen_addresses = ['0.0.0.0:53']
55c55
< # user_name = 'nobody'
---
> user_name = 'nobody'
64c64
< ipv6_servers = false
---
> ipv6_servers = true
```

