#!/usr/bin/env python3
"""Hook for PermissionRequest — marks session as pending_approval."""
from _common import run_hook

if __name__ == '__main__':
    run_hook("PermissionRequest")
