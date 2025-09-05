# Copyright 2025 Canonical
# See LICENSE file for licensing details.
"""Utils for the nginx package."""

import subprocess


def is_ipv6_enabled() -> bool:
    """Check if IPv6 is enabled on the container's network interfaces."""
    try:
        output = subprocess.run(
            ['ip', '-6', 'address', 'show'], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError:
        # if running the command failed for any reason, assume ipv6 is not enabled.
        return False
    return bool(output.stdout)
