#!/usr/bin/env python3
"""
Test wrapper script for dnscrypt-proxy container testing with intelligent exit codes.

This script runs pytest tests and translates the results to the appropriate exit codes
for CI integration, maintaining compatibility with the existing shell script interface.

Usage: python test_container.py [IMAGE_NAME]

Exit codes:
- 0: All tests passed (container fully functional)
- 1: Critical infrastructure failure (container build/startup problems)  
- 2: Network-dependent tests failed but infrastructure is OK (expected in restricted environments)
"""

import sys
import os
import subprocess
import argparse


def main():
    parser = argparse.ArgumentParser(description="Test dnscrypt-proxy Docker container")
    parser.add_argument("image_name", nargs="?", 
                       default=os.environ.get("TEST_IMAGE_NAME", "nathanhowell/dnscrypt-proxy:latest"),
                       help="Docker image name to test")
    parser.add_argument("--build", action="store_true",
                       help="Build the image before testing")
    parser.add_argument("--dry-run", action="store_true",
                       help="Validate test structure without running containers")
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("Running dry-run validation of test structure...")
        try:
            import test_dnscrypt_proxy
            critical_class = test_dnscrypt_proxy.TestCriticalInfrastructure
            network_class = test_dnscrypt_proxy.TestNetworkDependent
            
            critical_methods = [m for m in dir(critical_class) if m.startswith('test_')]
            network_methods = [m for m in dir(network_class) if m.startswith('test_')]
            
            print(f"✓ Test module loaded successfully")
            print(f"✓ Critical infrastructure tests: {len(critical_methods)}")
            print(f"✓ Network-dependent tests: {len(network_methods)}")
            print(f"✓ Total test methods: {len(critical_methods) + len(network_methods)}")
            print("✓ Dry-run validation passed - test structure is valid")
            return 0
        except Exception as e:
            print(f"✗ Dry-run validation failed: {e}")
            return 1
    
    # Set environment variables for the test
    os.environ["TEST_IMAGE_NAME"] = args.image_name
    if args.build:
        os.environ["BUILD_IMAGE"] = "true"
    
    print(f"Running comprehensive sanity test for dnscrypt-proxy image: {args.image_name}")
    
    # Install dependencies if needed
    try:
        import pytest
        import docker
        import colorama
    except ImportError:
        print("Installing required dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    
    # Clean up any existing exit code file
    exit_code_file = "/tmp/pytest_exit_code"
    if os.path.exists(exit_code_file):
        os.remove(exit_code_file)
    
    # Run pytest
    pytest_cmd = [sys.executable, "-m", "pytest", "test_dnscrypt_proxy.py", "-v"]
    
    try:
        # Run pytest - it may exit with various codes, but we want our intelligent codes
        subprocess.run(pytest_cmd)
        
        # Read the intelligent exit code set by our session finish handler
        if os.path.exists(exit_code_file):
            with open(exit_code_file, 'r') as f:
                intelligent_exit_code = int(f.read().strip())
            os.remove(exit_code_file)
            sys.exit(intelligent_exit_code)
        else:
            # Fallback - if no exit code file, assume critical failure
            sys.exit(1)
            
    except subprocess.CalledProcessError as e:
        # pytest failed to run at all
        print(f"Error running tests: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())