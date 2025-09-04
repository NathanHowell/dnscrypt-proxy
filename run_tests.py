#!/usr/bin/env python3
"""
Test runner script for dnscrypt-proxy Docker container tests.

This script runs pytest with intelligent exit code handling for CI integration.
It maintains compatibility with the original shell script interface while using
pure Python and pytest.

Usage: python run_tests.py [IMAGE_NAME] [--build] [--help]

Exit codes:
- 0: All tests passed (container fully functional)
- 1: Critical infrastructure failure (container build/startup problems)
- 2: Network-dependent tests failed but infrastructure is OK (expected in restricted environments)
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Test dnscrypt-proxy Docker container with pytest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0 - All tests passed (container fully functional)
  1 - Critical infrastructure failure (real container problems)
  2 - Network-dependent tests failed (expected in restricted networks)
        
Examples:
  python run_tests.py                                    # Test default image
  python run_tests.py nathanhowell/dnscrypt-proxy:latest # Test specific image  
  python run_tests.py --build                            # Build and test local image
        """
    )
    
    parser.add_argument(
        "image_name", 
        nargs="?",
        default=os.environ.get("TEST_IMAGE_NAME", "nathanhowell/dnscrypt-proxy:latest"),
        help="Docker image name to test (default: nathanhowell/dnscrypt-proxy:latest)"
    )
    parser.add_argument(
        "--build", 
        action="store_true",
        help="Build the Docker image before testing"
    )
    parser.add_argument(
        "--verbose", 
        "-v",
        action="store_true", 
        help="Enable verbose test output"
    )
    
    args = parser.parse_args()
    
    # Set environment variables for pytest
    os.environ["TEST_IMAGE_NAME"] = args.image_name
    if args.build:
        os.environ["BUILD_IMAGE"] = "true"
    
    print(f"Running dnscrypt-proxy container tests for image: {args.image_name}")
    if args.build:
        print("Building image before testing...")
    print()
    
    # Build pytest command
    pytest_args = [
        sys.executable, "-m", "pytest", 
        "tests/",
        "--tb=short"
    ]
    
    if args.verbose:
        pytest_args.append("-v")
    else:
        pytest_args.extend(["-q", "--tb=line"])
    
    # Run pytest
    try:
        result = subprocess.run(pytest_args, cwd=Path(__file__).parent)
        pytest_exit_code = result.returncode
        
        # Check for custom exit code from our session finish handler
        custom_exit_code = os.environ.get('PYTEST_DNSCRYPT_EXIT_CODE')
        if custom_exit_code:
            exit_code = int(custom_exit_code)
            # Clean up the environment variable
            del os.environ['PYTEST_DNSCRYPT_EXIT_CODE']
        else:
            # Map pytest exit codes to our intelligent codes
            if pytest_exit_code == 0:
                exit_code = 0  # All tests passed
            else:
                # For any pytest failure, we need to determine if it's critical or network
                # Since we're using pytest.skip for network issues, failures indicate critical issues
                exit_code = 1  # Critical failure
        
        return exit_code
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())