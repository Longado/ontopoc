"""Database passwords, kept in the workspace file sealed with a key that lives in a file of its own beside it.

This is obfuscation at rest, not a safe: the key file sits in the same data directory, so whoever can read that directory can read the passwords. What it
does is keep a password out of a copied or backed-up workspace.sqlite, a database dump and any screen that prints a row of it. The key file is made once,
mode 600. Standard library only (no cryptography package): the keystream is HMAC-SHA256 in counter mode and a second HMAC over the nonce and the cipher text is
checked before anything is decrypted, so a changed value is refused, not read as garbage. An OS keychain would be the real fix; until then say "obscured".
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

KEY_FILE = 'sources.key'
_VERSION = b'\x01'
_ephemeral: dict[str, bytes] = {}   # a workspace with no file (tests): one key for the life of the process


class VaultError(ValueError):
    """A sealed value that cannot be opened (the key file is gone or is another one, or the value was changed)."""


def _master(directory: Path | None) -> bytes:
    if directory is None:
        return _ephemeral.setdefault('memory', secrets.token_bytes(32))
    path = directory / KEY_FILE
    if not path.exists():
        # written whole to a file of its own (mode 600 from the start) and linked into place: a crash leaves no half-written key, and of two first callers one wins
        temporary = directory / f'.{KEY_FILE}.{secrets.token_hex(4)}'
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(secrets.token_bytes(32))
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass   # another caller got there first: its key is the key
        finally:
            os.unlink(temporary)
    key = path.read_bytes()
    if len(key) != 32:
        raise VaultError(f'{KEY_FILE} 不是一把有效的钥匙（应是 32 个字节），数据源的密码读不出来；不要手改它')
    if path.stat().st_mode & 0o077:
        os.chmod(path, 0o600)   # a key file that someone made readable is closed again
    return key


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = (hmac.new(key, nonce + counter.to_bytes(8, 'big'), hashlib.sha256).digest() for counter in range((length + 31) // 32))
    return b''.join(blocks)[:length]


def _subkeys(directory: Path | None) -> tuple[bytes, bytes]:
    master = _master(directory)
    return hmac.new(master, b'encrypt', hashlib.sha256).digest(), hmac.new(master, b'authenticate', hashlib.sha256).digest()


def seal(directory: Path | None, plain: str) -> str:
    encrypt, authenticate = _subkeys(directory)
    data, nonce = plain.encode('utf-8'), secrets.token_bytes(16)
    body = bytes(a ^ b for a, b in zip(data, _stream(encrypt, nonce, len(data))))
    tag = hmac.new(authenticate, _VERSION + nonce + body, hashlib.sha256).digest()
    return base64.b64encode(_VERSION + nonce + body + tag).decode('ascii')


def unseal(directory: Path | None, sealed: str) -> str:
    encrypt, authenticate = _subkeys(directory)
    try:
        raw = base64.b64decode(sealed, validate=True)
    except ValueError:
        raise VaultError('数据源的密码记录坏了，请重新填一次密码') from None
    nonce, body, tag = raw[1:17], raw[17:-32], raw[-32:]
    if raw[:1] != _VERSION or len(raw) < 49 or not hmac.compare_digest(tag, hmac.new(authenticate, _VERSION + nonce + body, hashlib.sha256).digest()):
        raise VaultError('数据源的密码打不开（钥匙文件换过或记录被改过），请重新填一次密码')
    return bytes(a ^ b for a, b in zip(body, _stream(encrypt, nonce, len(body)))).decode('utf-8')
