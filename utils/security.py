import hashlib
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return salt.hex() + ":" + hashed.hex()


def verify_password(stored_password_hash: str, provided_password: str) -> bool:
    if not stored_password_hash or ":" not in stored_password_hash:
        return False
    try:
        salt_hex, hash_hex = stored_password_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        hashed = hashlib.pbkdf2_hmac(
            "sha256", provided_password.encode("utf-8"), salt, 100000
        )
        return hashed == expected
    except Exception:
        return False
