#!/usr/bin/env python3
"""Hook for PermissionRequest — marks session as pending_approval.

`decide=True` additionally lets a connected cc-monitor UI answer the prompt:
the hook holds the terminal dialog open and long-polls for a remote decision.
When nothing answers within the hold window (or no UI is connected at all) the
hook exits silently and the normal local dialog appears, unchanged.
"""
from _common import run_hook

if __name__ == '__main__':
    run_hook("PermissionRequest", decide=True)
