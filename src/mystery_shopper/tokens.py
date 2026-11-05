"""Run tokens: short identifiers that scope every row and ID in one run."""
from __future__ import annotations

import random
import re

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def new_token(rng: random.Random) -> str:
    """Return a fresh run token: 'R' plus 4 characters from [A-Z0-9]."""
    return "R" + "".join(rng.choice(_ALPHABET) for _ in range(4))


def scoped_id(base: str, token: str) -> str:
    """Scope an entity id to a run token: 'A1043' + 'R7K2' -> 'A1043-R7K2'."""
    return f"{base}-{token}"


def scoped_email(local: str, token: str) -> str:
    """Scope a local-part email to a run token."""
    return f"{local}.{token.lower()}@example.com"


def token_in(text: str) -> str | None:
    """Find a run token in free text: '-Rxxxx' or '.rxxxx@'. Upper-cased."""
    m = re.search(r"-(R[A-Za-z0-9]+)\b", text)
    if m:
        return m.group(1).upper()
    m = re.search(r"\.(r[A-Za-z0-9]+)@", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None
