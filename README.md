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

To test that the container starts correctly and accepts traffic:

```bash
# Test a pre-built image from Docker Hub
./test-sanity.sh nathanhowell/dnscrypt-proxy:latest

# Test a locally built image  
./test-container.sh  # Builds and tests the image
```

The sanity test validates:
- Container starts and runs correctly
- dnscrypt-proxy process is running
- Ports are bound and listening
- Configuration is loaded properly
- Container would accept traffic in normal network conditions

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

