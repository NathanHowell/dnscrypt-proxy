#!/usr/bin/env python3
"""
Container sanity test for dnscrypt-proxy Docker image using pytest.

This is a compatibility wrapper that maintains the same interface as test-sanity.sh
but uses the Python pytest implementation.

Usage: python test_sanity.py [IMAGE_NAME]

Exit codes:
- 0: All tests passed (container fully functional)
- 1: Critical infrastructure failure (container build/startup problems)
- 2: Network-dependent tests failed but infrastructure is OK (expected in restricted environments)
"""

import sys
import os

# Import the test container module
from test_container import main

if __name__ == "__main__":
    # This is just a wrapper to maintain compatibility
    main()