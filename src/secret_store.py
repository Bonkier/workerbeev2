"""Windows DPAPI wrapper for encrypting/decrypting secrets at rest.

Secrets are encrypted with the current user's Windows login. Even another
user on the same PC cannot decrypt them.
"""

import base64
import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger(__name__)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32


def _blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    b = _DATA_BLOB()
    b.cbData = len(data)
    b.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
    b._buf = buf  # keep reference
    return b


def _from_blob(b: _DATA_BLOB) -> bytes:
    data = ctypes.string_at(b.pbData, b.cbData)
    _kernel32.LocalFree(b.pbData)
    return data


def encrypt(plaintext: str) -> str:
    """Encrypt a string; returns base64-encoded ciphertext."""
    if not plaintext:
        return ''
    src = _blob(plaintext.encode('utf-8'))
    out = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)
    )
    if not ok:
        logger.error("CryptProtectData failed")
        return ''
    return 'dpapi:' + base64.b64encode(_from_blob(out)).decode('ascii')


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64 ciphertext produced by encrypt(). Returns '' on failure."""
    if not ciphertext:
        return ''
    if not ciphertext.startswith('dpapi:'):
        return ciphertext
    try:
        raw = base64.b64decode(ciphertext[6:])
    except Exception:
        return ''
    src = _blob(raw)
    out = _DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)
    )
    if not ok:
        return ''
    try:
        return _from_blob(out).decode('utf-8', errors='replace')
    except Exception:
        return ''
