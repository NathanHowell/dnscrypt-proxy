#!/usr/bin/env python3
"""
Comprehensive dnscrypt-proxy Docker container tests using pytest.

This module provides intelligent test categorization with meaningful CI feedback:
- Critical infrastructure tests (must pass): container startup, port binding, configuration
- Network-dependent tests (may fail in restricted environments): DNS resolution, upstream connections

Exit codes:
- 0: All tests passed (container fully functional)
- 1: Critical infrastructure failure (container build/startup problems)
- 2: Network-dependent tests failed but infrastructure is OK (expected in restricted environments)
"""

import os
import sys
import time
import socket
import subprocess
import logging
import docker
import pytest
from typing import Optional, Tuple
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Test configuration
DEFAULT_IMAGE_NAME = "nathanhowell/dnscrypt-proxy:latest"
TEST_CONTAINER_NAME = "dnscrypt-proxy-pytest-test"
TEST_PORT = 15353
CONTAINER_INIT_WAIT = 10
CONTAINER_STABILITY_WAIT = 5

# Test result tracking
critical_failures = 0
network_failures = 0

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestResult:
    """Track test results and categorize failures."""
    
    def __init__(self):
        self.critical_failures = 0
        self.network_failures = 0
        self.critical_tests = 0
        self.network_tests = 0
    
    def record_result(self, test_name: str, passed: bool, test_type: str):
        """Record a test result."""
        if test_type == "critical":
            self.critical_tests += 1
            if not passed:
                self.critical_failures += 1
        else:  # network
            self.network_tests += 1
            if not passed:
                self.network_failures += 1
        
        status = f"{Fore.GREEN}✓{Style.RESET_ALL}" if passed else f"{Fore.RED}✗{Style.RESET_ALL}"
        print(f"{status} {test_name}")
    
    def get_exit_code(self) -> int:
        """Determine appropriate exit code based on test results."""
        if self.critical_failures > 0:
            return 1  # Critical infrastructure failure
        elif self.network_failures > 0:
            return 2  # Network-dependent failures only
        return 0  # All tests passed


# Global test result tracker
test_results = TestResult()


class DnscryptProxyContainerTest:
    """Test fixture for dnscrypt-proxy container testing."""
    
    def __init__(self, image_name: str = None):
        self.docker_client = docker.from_env()
        self.image_name = image_name or DEFAULT_IMAGE_NAME
        self.container = None
        self.container_logs = ""
    
    def setup_container(self, build_image: bool = False) -> bool:
        """Set up the container for testing."""
        try:
            # Handle image availability
            if build_image:
                logger.info("Building Docker image...")
                try:
                    self.docker_client.images.build(path=".", tag="dnscrypt-proxy-test")
                    self.image_name = "dnscrypt-proxy-test"
                except docker.errors.BuildError as e:
                    logger.error("Failed to build Docker image")
                    logger.error("This may be due to network restrictions preventing access to package repositories.")
                    return False
            else:
                # Check if image exists locally, pull if needed
                try:
                    self.docker_client.images.get(self.image_name)
                    logger.info(f"Image {self.image_name} found locally")
                except docker.errors.ImageNotFound:
                    logger.info(f"Image {self.image_name} not found locally")
                    if os.environ.get("CI") == "true":
                        logger.info("Running in CI environment - checking for similar images...")
                        images = self.docker_client.images.list()
                        suitable_image = None
                        for img in images:
                            for tag in img.tags:
                                if "nathanhowell/dnscrypt-proxy" in tag:
                                    suitable_image = tag
                                    break
                            if suitable_image:
                                break
                        
                        if suitable_image:
                            logger.info(f"Using available image: {suitable_image}")
                            self.image_name = suitable_image
                        else:
                            logger.warning("No suitable image found in CI environment, attempting to pull...")
                            try:
                                self.docker_client.images.pull(self.image_name)
                            except docker.errors.APIError:
                                logger.error(f"Failed to pull image {self.image_name} - this may be due to network restrictions")
                                return False
                    else:
                        logger.info(f"Pulling image {self.image_name}...")
                        try:
                            self.docker_client.images.pull(self.image_name)
                        except docker.errors.APIError:
                            logger.error(f"Failed to pull image {self.image_name}")
                            return False
            
            # Start container
            logger.info(f"Starting dnscrypt-proxy container on port {TEST_PORT}...")
            self.container = self.docker_client.containers.run(
                self.image_name,
                detach=True,
                name=TEST_CONTAINER_NAME,
                ports={'53/udp': TEST_PORT},
                remove=False  # We'll clean up manually for better control
            )
            
            # Wait for initialization
            logger.info("Waiting for container to initialize...")
            time.sleep(CONTAINER_INIT_WAIT)
            
            # Refresh container state and get logs
            self.container.reload()
            self.container_logs = self.container.logs().decode('utf-8', errors='ignore')
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set up container: {e}")
            return False
    
    def cleanup_container(self):
        """Clean up test container."""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
                logger.info("Container cleaned up successfully")
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")
        
        # Clean up any leftover containers
        try:
            existing = self.docker_client.containers.get(TEST_CONTAINER_NAME)
            existing.stop()
            existing.remove()
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Error cleaning up existing container: {e}")
    
    def get_container_status(self) -> str:
        """Get current container status."""
        if not self.container:
            return "not_created"
        
        try:
            self.container.reload()
            return self.container.status
        except Exception:
            return "unknown"
    
    def check_port_binding(self) -> bool:
        """Check if the test port is bound on the host."""
        try:
            result = subprocess.run(['ss', '-lun'], capture_output=True, text=True, timeout=5)
            return f":{TEST_PORT} " in result.stdout
        except Exception:
            return False
    
    def test_dns_connectivity(self) -> bool:
        """Test basic DNS connectivity."""
        try:
            # Create a simple DNS query packet
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            
            # Simple DNS query for example.com (A record)
            query = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01'
            sock.sendto(query, ('127.0.0.1', TEST_PORT))
            
            # Try to receive response
            data = sock.recv(1024)
            sock.close()
            
            return len(data) > 0
            
        except Exception:
            return False
    
    def run_dig_test(self, domain: str = "example.com", record_type: str = "A") -> Tuple[bool, str]:
        """Run a dig command test."""
        try:
            cmd = [
                'dig', f'@127.0.0.1', '-p', str(TEST_PORT),
                '+time=5', '+tries=2', domain, record_type
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            output = result.stdout + result.stderr
            success = "ANSWER SECTION" in output
            
            return success, output
            
        except subprocess.TimeoutExpired:
            return False, "DNS query timed out"
        except FileNotFoundError:
            return False, "dig command not found"
        except Exception as e:
            return False, f"DNS query failed: {e}"


@pytest.fixture(scope="session")
def container_test():
    """Pytest fixture for container testing."""
    image_name = os.environ.get("TEST_IMAGE_NAME", DEFAULT_IMAGE_NAME)
    build_image = os.environ.get("BUILD_IMAGE", "false").lower() == "true"
    
    test_instance = DnscryptProxyContainerTest(image_name)
    
    if not test_instance.setup_container(build_image=build_image):
        test_results.record_result("Container setup", False, "critical")
        pytest.exit("Failed to set up container - critical infrastructure failure")
    
    yield test_instance
    
    test_instance.cleanup_container()


class TestCriticalInfrastructure:
    """Critical infrastructure tests - these must pass for the container to be considered functional."""
    
    def test_container_is_running(self, container_test):
        """Test that the container starts and stays running."""
        status = container_test.get_container_status()
        passed = status == "running"
        test_results.record_result("Container is running", passed, "critical")
        
        if not passed:
            logger.error(f"Container status: {status}")
            if container_test.container_logs:
                logger.error("Container logs:")
                logger.error(container_test.container_logs)
        
        assert passed, f"Container is not running (status: {status})"
    
    def test_no_critical_startup_errors(self, container_test):
        """Test that there are no critical startup errors in container logs."""
        logs = container_test.container_logs
        
        # Look for critical errors but exclude network-related issues
        critical_patterns = ["FATAL", "failed to bind", "permission denied", "cannot allocate"]
        network_patterns = ["network", "connection", "timeout", "unreachable", "refused", "dial tcp"]
        
        critical_errors = []
        for line in logs.split('\n'):
            line_lower = line.lower()
            if any(pattern in line_lower for pattern in critical_patterns):
                # Check if it's actually a network-related error
                if not any(net_pattern in line_lower for net_pattern in network_patterns):
                    critical_errors.append(line)
        
        passed = len(critical_errors) == 0
        test_results.record_result("No critical startup errors", passed, "critical")
        
        if not passed:
            logger.error("Critical startup errors found:")
            for error in critical_errors:
                logger.error(error)
        
        assert passed, f"Critical startup errors found: {critical_errors}"
    
    def test_configuration_file_loaded(self, container_test):
        """Test that the configuration file is loaded."""
        logs = container_test.container_logs
        config_patterns = ["Configuration file", "config.*loaded", "reading.*config"]
        
        passed = any(pattern.lower() in logs.lower() for pattern in config_patterns)
        test_results.record_result("Configuration file loaded", passed, "critical")
        
        assert passed, "Configuration file loading not detected in logs"
    
    def test_host_port_binding(self, container_test):
        """Test that the host port is properly bound."""
        # Give a moment for port binding
        time.sleep(2)
        
        passed = container_test.check_port_binding()
        test_results.record_result("Host port binding", passed, "critical")
        
        assert passed, f"Port {TEST_PORT} is not bound on host"
    
    def test_container_stability(self, container_test):
        """Test that the container doesn't crash immediately."""
        time.sleep(CONTAINER_STABILITY_WAIT)
        
        status = container_test.get_container_status()
        passed = status == "running"
        test_results.record_result("Container stability (doesn't crash)", passed, "critical")
        
        assert passed, f"Container is not stable (status: {status})"


class TestNetworkDependent:
    """Network-dependent tests - these may fail in restricted environments."""
    
    def test_dnscrypt_proxy_process_running(self, container_test):
        """Test that the dnscrypt-proxy process is running inside the container."""
        try:
            result = container_test.container.exec_run("ps aux")
            output = result.output.decode('utf-8', errors='ignore')
            
            passed = "dnscrypt-proxy" in output and "grep" not in output
            
            if not passed:
                # Check if process exit appears to be network-related
                logs = container_test.container_logs
                network_errors = ["network.*error", "connection.*failed", "timeout", "unreachable", "dial tcp.*refused"]
                
                if any(pattern in logs.lower() for pattern in network_errors):
                    logger.warning("Process exit appears to be network-related (expected in restricted environments)")
                    test_results.record_result("dnscrypt-proxy process running", False, "network")
                else:
                    logger.error("Process exit may indicate a configuration or startup problem")
                    test_results.record_result("dnscrypt-proxy process running", False, "critical")
            else:
                test_results.record_result("dnscrypt-proxy process running", True, "network")
            
        except Exception as e:
            logger.error(f"Failed to check process status: {e}")
            test_results.record_result("dnscrypt-proxy process running", False, "network")
    
    def test_udp_port_listening(self, container_test):
        """Test that UDP port 53 is listening inside the container."""
        logs = container_test.container_logs
        passed = "Now listening to 0.0.0.0:53 [UDP]" in logs
        test_results.record_result("UDP port 53 listening", passed, "network")
    
    def test_tcp_port_listening(self, container_test):
        """Test that TCP port 53 is listening inside the container."""
        logs = container_test.container_logs
        passed = "Now listening to 0.0.0.0:53 [TCP]" in logs
        test_results.record_result("TCP port 53 listening", passed, "network")
    
    def test_public_resolvers_loaded(self, container_test):
        """Test that public resolvers configuration is loaded."""
        logs = container_test.container_logs
        passed = "Source [public-resolvers] loaded" in logs
        test_results.record_result("Public resolvers configuration loaded", passed, "network")
    
    def test_upstream_dns_resolution_attempts(self, container_test):
        """Test that upstream DNS server resolution attempts are made."""
        logs = container_test.container_logs
        passed = "Resolving server host" in logs
        test_results.record_result("Upstream DNS server resolution attempts", passed, "network")
    
    def test_container_health_check(self, container_test):
        """Test container health check status."""
        try:
            time.sleep(5)  # Wait for health check
            container_test.container.reload()
            
            # Get health status
            inspect_data = container_test.docker_client.api.inspect_container(container_test.container.id)
            health_status = inspect_data.get('State', {}).get('Health', {}).get('Status', 'no-healthcheck')
            
            if health_status == "healthy":
                test_results.record_result("Container health check", True, "network")
            elif health_status == "starting":
                test_results.record_result("Container health check", False, "network")  # Inconclusive, but record as network issue
                logger.info("Health check still starting")
            elif health_status == "no-healthcheck":
                test_results.record_result("Container health check", False, "network")  # Inconclusive
                logger.info("No health check configured")
            else:
                test_results.record_result("Container health check", False, "network")
                logger.warning(f"Health check status: {health_status}")
                
        except Exception as e:
            logger.error(f"Failed to check container health: {e}")
            test_results.record_result("Container health check", False, "network")
    
    def test_port_connectivity(self, container_test):
        """Test basic port connectivity."""
        passed = container_test.test_dns_connectivity()
        test_results.record_result("Port connectivity test", passed, "network")
    
    def test_dns_query_example_com(self, container_test):
        """Test DNS query for example.com."""
        success, output = container_test.run_dig_test("example.com", "A")
        test_results.record_result("DNS query (example.com)", success, "network")
        
        if not success:
            logger.warning(f"DNS query output: {output}")
    
    def test_dns_query_google_com(self, container_test):
        """Test DNS query for google.com."""
        success, output = container_test.run_dig_test("google.com", "A")
        test_results.record_result("DNS query (google.com)", success, "network")
        
        if not success:
            logger.warning(f"DNS query output: {output}")


def pytest_sessionfinish(session, exitstatus):
    """Custom session finish handler to implement intelligent exit codes."""
    print("\n" + "="*60)
    print(f"{Fore.BLUE}TEST SUMMARY{Style.RESET_ALL}")
    print(f"Critical Infrastructure Tests: {test_results.critical_tests - test_results.critical_failures}/{test_results.critical_tests} passed")
    print(f"Network-Dependent Tests: {test_results.network_tests - test_results.network_failures}/{test_results.network_tests} passed")
    print("")
    
    # Get appropriate exit code
    intelligent_exit_code = test_results.get_exit_code()
    
    if intelligent_exit_code == 1:
        print(f"{Fore.RED}CRITICAL FAILURES DETECTED{Style.RESET_ALL}")
        print("The container has infrastructure problems that prevent normal operation.")
        print("This indicates a real issue with the container build or configuration.")
    elif intelligent_exit_code == 2:
        print(f"{Fore.YELLOW}NETWORK-DEPENDENT TESTS FAILED{Style.RESET_ALL}")
        print("The container infrastructure is functional, but network-dependent features failed.")
        print("This is expected in restricted network environments like CI.")
        print("In unrestricted environments, the container should function normally.")
    else:
        print(f"{Fore.GREEN}ALL TESTS PASSED{Style.RESET_ALL}")
        print("The container is fully functional and ready to accept DNS traffic.")
    
    print("="*60)
    
    # Store the intelligent exit code for the wrapper script
    with open('/tmp/pytest_exit_code', 'w') as f:
        f.write(str(intelligent_exit_code))


if __name__ == "__main__":
    # Allow running directly with python
    pytest.main([__file__] + sys.argv[1:])