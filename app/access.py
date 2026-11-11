from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Account:
    name: str
    key_hash: str = field(repr=False)
    github_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Access:
    origin: str
    hostname: str
    accounts: dict[str, Account]

    def authenticate(self, authorization: str) -> Account | None:
        try:
            if not authorization.startswith("Basic ") or len(authorization) > 1024:
                return None
            name, key = base64.b64decode(authorization[6:], validate=True).decode().split(":", 1)
            if not 32 <= len(key) <= 128:
                return None
        except (ValueError, UnicodeError):
            return None
        account = self.accounts.get(name)
        actual = hashlib.sha256(key.encode()).hexdigest()
        expected = account.key_hash if account else "0" * 64
        return account if hmac.compare_digest(actual, expected) else None


def access_configuration() -> Access | None:
    value = os.getenv("QUORUM_PUBLIC_ORIGIN", "")
    if not value:
        if os.getenv("QUORUM_USERS"):
            raise ValueError("QUORUM_USERS requires an explicit HTTPS QUORUM_PUBLIC_ORIGIN")
        return None
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ValueError("QUORUM_PUBLIC_ORIGIN must be an exact HTTPS origin")
    records = json.loads(os.getenv("QUORUM_USERS", "{}"))
    if not isinstance(records, dict) or not 1 <= len(records) <= 50:
        raise ValueError("Configure 1–50 individual users in QUORUM_USERS")
    accounts = {}
    for name, settings in records.items():
        if (
            not re.fullmatch(r"[a-z0-9_-]{3,64}", name)
            or not isinstance(settings, dict)
            or not re.fullmatch(r"[a-f0-9]{64}", settings.get("key_hash", ""))
        ):
            raise ValueError("Each user needs a stable name and SHA-256 key_hash")
        token = settings.get("github_token")
        if token is not None and (not isinstance(token, str) or len(token) > 512):
            raise ValueError("Invalid account GitHub credential")
        accounts[name] = Account(name, settings["key_hash"], token or None)
    return Access(value.rstrip("/"), url.hostname, accounts)
