"""Generate a private individual access key; print only when explicitly run by the operator."""

import argparse
import hashlib
import json
import re
import secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    name = parser.parse_args().name
    if not re.fullmatch(r"[a-z0-9_-]{3,64}", name):
        parser.error("Use 3–64 lowercase letters, digits, underscores or hyphens")
    key = secrets.token_urlsafe(36)
    print(
        json.dumps(
            {
                "username": name,
                "access_key": key,
                "configuration": {name: {"key_hash": hashlib.sha256(key.encode()).hexdigest()}},
            }
        )
    )


if __name__ == "__main__":
    main()
