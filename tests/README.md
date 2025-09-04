# dnscrypt-proxy Container Tests

This directory contains comprehensive pytest-based tests for the dnscrypt-proxy Docker container.

## Test Structure

- `conftest.py` - Pytest configuration, fixtures, and shared test utilities
- `test_dnscrypt_proxy.py` - Main test suite with critical infrastructure and network-dependent tests

## Test Categories

### Critical Infrastructure Tests (`@pytest.mark.critical`)
These tests must pass and indicate real container problems if they fail:
- Container startup and stability
- Port binding and configuration loading
- Critical error detection

### Network-Dependent Tests (`@pytest.mark.network`) 
These tests may fail in restricted network environments like CI:
- DNS resolution and upstream connections
- Process health in restricted networks
- Network connectivity validation

## Running Tests

From the repository root:

```bash
# Install dependencies
uv sync

# Run all tests
uv run python run_tests.py

# Test specific image
uv run python run_tests.py nathanhowell/dnscrypt-proxy:latest

# Build and test locally
uv run python run_tests.py --build

# Verbose output
uv run python run_tests.py --verbose
```

## Exit Codes

- **0**: All tests passed (container fully functional)
- **1**: Critical infrastructure failure (real container problems)
- **2**: Network-dependent tests failed (expected in restricted environments)

This intelligent exit code system provides meaningful CI feedback while handling network restrictions gracefully.