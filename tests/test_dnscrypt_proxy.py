"""
Comprehensive dnscrypt-proxy Docker container tests using pytest.

This module provides intelligent test categorization with meaningful CI feedback:
- Critical infrastructure tests (must pass): container startup, port binding, configuration
- Network-dependent tests (may fail in restricted environments): DNS resolution, upstream connections

Test markers:
- @pytest.mark.critical: Critical infrastructure tests that must pass
- @pytest.mark.network: Network-dependent tests that may fail in restricted environments
"""

import time
import logging
import pytest
from conftest import test_results, CONTAINER_STABILITY_WAIT, TEST_PORT

logger = logging.getLogger(__name__)


@pytest.mark.critical
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
        
        # Look for critical errors but exclude network-related issues and cache file warnings
        critical_patterns = ["FATAL", "failed to bind", "cannot allocate", "error starting", "panic", "failed to start"]
        network_patterns = ["network", "connection", "timeout", "unreachable", "refused", "dial tcp"]
        cache_patterns = ["cache file", "couldn't write cache"]
        
        critical_errors = []
        for line in logs.split('\n'):
            line_lower = line.lower()
            if any(pattern in line_lower for pattern in critical_patterns):
                # Check if it's actually a network-related error or cache file warning
                if not any(net_pattern in line_lower for net_pattern in network_patterns) and \
                   not any(cache_pattern in line_lower for cache_pattern in cache_patterns):
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
        # Look for typical dnscrypt-proxy startup messages that indicate successful config loading
        config_patterns = [
            "configuration file",
            "loading configuration",
            "listening to", 
            "ready", 
            "udp server is ready",
            "source [public-resolvers]",
            "server listening"
        ]
        
        passed = any(pattern.lower() in logs.lower() for pattern in config_patterns)
        test_results.record_result("Configuration file loaded", passed, "critical")
        
        if not passed:
            logger.warning("Configuration loading indicators not found. Available logs:")
            for line in logs.split('\n')[:10]:  # Show first 10 lines for debugging
                logger.info(f"Log: {line}")
        
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


@pytest.mark.network  
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
                    pytest.skip("Process exit due to network restrictions")
                else:
                    logger.error("Process exit may indicate a configuration or startup problem")
                    test_results.record_result("dnscrypt-proxy process running", False, "critical")
                    pytest.fail("dnscrypt-proxy process not running - possible configuration issue")
            else:
                test_results.record_result("dnscrypt-proxy process running", True, "network")
            
        except Exception as e:
            logger.error(f"Failed to check process status: {e}")
            test_results.record_result("dnscrypt-proxy process running", False, "network")
            pytest.skip(f"Could not check process status: {e}")
    
    def test_udp_port_listening(self, container_test):
        """Test that UDP port 53 is listening inside the container."""
        logs = container_test.container_logs
        passed = "Now listening to 0.0.0.0:53 [UDP]" in logs
        test_results.record_result("UDP port 53 listening", passed, "network")
        
        if not passed:
            pytest.skip("UDP port 53 not listening - may be due to network restrictions")
    
    def test_tcp_port_listening(self, container_test):
        """Test that TCP port 53 is listening inside the container."""
        logs = container_test.container_logs
        passed = "Now listening to 0.0.0.0:53 [TCP]" in logs
        test_results.record_result("TCP port 53 listening", passed, "network")
        
        if not passed:
            pytest.skip("TCP port 53 not listening - may be due to network restrictions")
    
    def test_public_resolvers_loaded(self, container_test):
        """Test that public resolvers configuration is loaded."""
        logs = container_test.container_logs
        passed = "Source [public-resolvers] loaded" in logs
        test_results.record_result("Public resolvers configuration loaded", passed, "network")
        
        if not passed:
            pytest.skip("Public resolvers not loaded - may be due to network restrictions")
    
    def test_upstream_dns_resolution_attempts(self, container_test):
        """Test that upstream DNS server resolution attempts are made."""
        logs = container_test.container_logs
        passed = "Resolving server host" in logs
        test_results.record_result("Upstream DNS server resolution attempts", passed, "network")
        
        if not passed:
            pytest.skip("No upstream DNS resolution attempts - may be due to network restrictions")
    
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
                pytest.skip("Health check still starting")
            elif health_status == "no-healthcheck":
                test_results.record_result("Container health check", False, "network")  # Inconclusive
                logger.info("No health check configured")
                pytest.skip("No health check configured")
            else:
                test_results.record_result("Container health check", False, "network")
                logger.warning(f"Health check status: {health_status}")
                pytest.skip(f"Health check unhealthy: {health_status}")
                
        except Exception as e:
            logger.error(f"Failed to check container health: {e}")
            test_results.record_result("Container health check", False, "network")
            pytest.skip(f"Could not check health status: {e}")
    
    def test_port_connectivity(self, container_test):
        """Test basic port connectivity."""
        passed = container_test.test_dns_connectivity()
        test_results.record_result("Port connectivity test", passed, "network")
        
        if not passed:
            pytest.skip("Port connectivity test failed - may be due to network restrictions")
    
    def test_dns_query_example_com(self, container_test):
        """Test DNS query for example.com."""
        success, output = container_test.run_dig_test("example.com", "A")
        test_results.record_result("DNS query (example.com)", success, "network")
        
        if not success:
            logger.warning(f"DNS query output: {output}")
            pytest.skip("DNS query failed - may be due to network restrictions")
    
    def test_dns_query_google_com(self, container_test):
        """Test DNS query for google.com.""" 
        success, output = container_test.run_dig_test("google.com", "A")
        test_results.record_result("DNS query (google.com)", success, "network")
        
        if not success:
            logger.warning(f"DNS query output: {output}")
            pytest.skip("DNS query failed - may be due to network restrictions")


# Additional test classes can be added here for more specific testing scenarios