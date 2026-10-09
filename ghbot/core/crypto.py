"""Symmetric encryption for tokens-at-rest and the state checkpoint.

AES-256-GCM with a key derived from STATE_KEY via scrypt.  The salt is random per
blob and prepended, so the same plaintext never produces the same ciphertext.
Format:  b"GB1" | salt(16) | nonce(12) | ciphertext+tag
"""

from __future__ import annotations

import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_MAGIC = b"GB1"


class DecryptError(Exception):
    pass


def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt(plaintext: bytes, passphrase: str) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext, _MAGIC)
    return _MAGIC + salt + nonce + ct


def decrypt(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(_MAGIC) or len(blob) < 3 + 16 + 12 + 16:
        raise DecryptError("not a GB1 blob")
    salt = blob[3:19]
    nonce = blob[19:31]
    ct = blob[31:]
    key = _derive(passphrase, salt)
    try:
        return AESGCM(key).decrypt(nonce, ct, _MAGIC)
    except InvalidTag as e:
        raise DecryptError("bad key or corrupted data") from e


def encrypt_str(text: str, passphrase: str) -> bytes:
    return encrypt(text.encode("utf-8"), passphrase)


def decrypt_str(blob: bytes, passphrase: str) -> str:
    return decrypt(blob, passphrase).decode("utf-8")


def new_session_id() -> str:
    return secrets.token_hex(8)
