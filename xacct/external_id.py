"""Create and check External IDs.

An External ID is a shared value the pipeline must send when it assumes the target role.
It is not a password (AWS shows it to anyone who can read the role), but it makes sure
only callers that were given the value can use the role. Treat it as confidential anyway.
"""

import re
import secrets

# AWS rule: 2-1224 characters of letters, digits and _ + = , . @ : / -
# This project asks for at least 32 characters so it cannot be guessed.
MIN_LENGTH = 32
MAX_LENGTH = 1224
_ALLOWED = re.compile(r"^[A-Za-z0-9_+=,.@:/-]+$")


def generate(length=48):
    """A new random External ID made of hex characters (always valid for AWS)."""
    if not MIN_LENGTH <= length <= MAX_LENGTH:
        raise ValueError(f"length must be between {MIN_LENGTH} and {MAX_LENGTH}")
    # token_hex(n) gives 2*n characters, so ask for half and trim.
    return secrets.token_hex((length + 1) // 2)[:length]


def validate(value):
    """Raise ValueError with a clear message if the External ID is not acceptable."""
    if not value:
        raise ValueError("the External ID is empty")
    if not MIN_LENGTH <= len(value) <= MAX_LENGTH:
        raise ValueError(f"the External ID must be {MIN_LENGTH}-{MAX_LENGTH} characters, it has {len(value)}")
    if not _ALLOWED.match(value):
        raise ValueError("the External ID may only contain letters, digits and _ + = , . @ : / -")
    return value
