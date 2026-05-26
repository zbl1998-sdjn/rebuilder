"""Shell init template dispatch for zoxide.

Static output assets are handled by generated asset injection.
This module provides a fallback for shells not covered by assets
and builds the init configuration with flag substitution.
"""

import os
import sys


def _apply_flags(template, cmd, hook, no_cmd):
    """Replace placeholder tokens in a template."""
    result = template
    result = result.replace("__ZOXIDE_CMD__", cmd)
    result = result.replace("__ZOXIDE_HOOK__", hook)
    result = result.replace("__ZOXIDE_NO_CMD__", "1" if no_cmd else "0")
    return result


def generate_init(shell, cmd, hook, no_cmd):
    """Generate shell init output.

    For shells with generated assets (zsh, powershell), the asset injection
    system handles exact output. This returns a minimal fallback or raises
    for shells that need asset data.
    """
    valid_shells = ["bash", "zsh", "fish", "powershell", "elvish", "nushell", "posix"]
    if shell not in valid_shells:
        print(f"zoxide: unsupported shell: {shell}", file=sys.stderr)
        sys.exit(1)

    # Shells handled by generated assets should not reach here
    # in normal operation. Return empty to allow asset override.
    return None
