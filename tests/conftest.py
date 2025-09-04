"""
Pytest configuration and shared fixtures for dnscrypt-proxy container testing.

This module provides pytest fixtures and configuration for testing the dnscrypt-proxy
Docker container with intelligent exit code handling for CI integration.
"""

import os
import sys
import time
import socket
import subprocess
import logging
import pytest
import docker
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestResult:
    """Track test results and categorize failures for intelligent exit codes."""
    
    def __init__(self):
        self.critical_failures = 0
        self.network_failures = 0
        self.critical_tests = 0
        self.network_tests = 0
        self.results = []
    
    def record_result(self, test_name: str, passed: bool, test_type: str):
        """Record a test result."""
        self.results.append({
            'name': test_name,
            'passed': passed,
            'type': test_type
        })
        
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

    def print_summary(self):
        """Print test summary with colored output."""
        print("\n" + "="*60)
        print(f"{Fore.BLUE}TEST SUMMARY{Style.RESET_ALL}")
        print(f"Critical Infrastructure Tests: {self.critical_tests - self.critical_failures}/{self.critical_tests} passed")
        print(f"Network-Dependent Tests: {self.network_tests - self.network_failures}/{self.network_tests} passed")
        print("")
        
        # Get appropriate exit code
        exit_code = self.get_exit_code()
        
        if exit_code == 1:
            print(f"{Fore.RED}CRITICAL FAILURES DETECTED{Style.RESET_ALL}")
            print("The container has infrastructure problems that prevent normal operation.")
            print("This indicates a real issue with the container build or configuration.")
        elif exit_code == 2:
            print(f"{Fore.YELLOW}NETWORK-DEPENDENT TESTS FAILED{Style.RESET_ALL}")
            print("The container infrastructure is functional, but network-dependent features failed.")
            print("This is expected in restricted network environments like CI.")
            print("In unrestricted environments, the container should function normally.")
        else:
            print(f"{Fore.GREEN}ALL TESTS PASSED{Style.RESET_ALL}")
            print("The container is fully functional and ready to accept DNS traffic.")
        
        print("="*60)


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


def pytest_sessionfinish(session, exitstatus):
    """Custom session finish handler to implement intelligent exit codes."""
    test_results.print_summary()
    
    # Store the intelligent exit code for CI integration
    intelligent_exit_code = test_results.get_exit_code()
    
    # Set the exit code by modifying the session's testsfailed count
    # This is a pytest-compatible way to control the exit code
    if intelligent_exit_code == 1:
        # Critical failures - pytest should exit with code 1
        session.testsfailed = max(session.testsfailed, 1)
    elif intelligent_exit_code == 2:
        # Network failures only - we want to exit with code 2
        # Create a custom exit mechanism for this case
        if hasattr(session.config, '_dnscrypt_exit_code'):
            session.config._dnscrypt_exit_code = 2
        else:
            # Fallback: store in environment for external handling
            os.environ['PYTEST_DNSCRYPT_EXIT_CODE'] = '2'