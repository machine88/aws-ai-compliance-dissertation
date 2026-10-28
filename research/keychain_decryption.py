"""Caller-owned macOS Keychain bridge for authenticated record decryption into private memory."""
import hashlib
import os
import platform
import stat
import subprocess
import tempfile
from pathlib import Path
from research.timing import require_sha256


def require_private_path(path, directory=False):
    """Reject symlinks, unowned paths and nonprivate recipient/scratch storage.

    Inputs:
        path: Existing path selected by the trusted local operator.
        directory: Whether to require an owned private directory rather than a regular file.
    Outputs:
        Path: Validated path; unsupported type, ownership or permissions raise ValueError.
    """
    path = Path(path)
    attributes = path.lstat()
    correct_type = stat.S_ISDIR(attributes.st_mode) if directory else stat.S_ISREG(attributes.st_mode)
    if not correct_type or attributes.st_uid != os.getuid() or attributes.st_mode & 0o077 or (not directory and attributes.st_nlink != 1):
        raise ValueError("Private owned non-symlink path required")
    return path


class MacKeychainDecryptor:
    """Provide the archive verifier with authenticated bytes; never return passphrases or keys."""

    def __init__(self, helper, helper_sha256, recipient, recipient_sha256, scratch):
        """Bind a trusted compiled helper and pinned local recipient before any key access.

        Inputs:
            helper: Owned private executable compiled from the reviewed macOS helper source.
            helper_sha256: Independently trusted compiled-helper fingerprint.
            recipient: Prepared owned private recipient directory.
            recipient_sha256: Independently pinned normalized public-certificate fingerprint.
            scratch: Owned private directory for temporary ciphertext copies only.
        Outputs:
            None: Stores validated references; makes no Keychain call or cloud request yet.
        """
        if platform.system() != "Darwin":
            raise ValueError("Local Keychain bridge requires macOS")
        require_sha256(helper_sha256)
        require_sha256(recipient_sha256)
        self.helper = require_private_path(helper)
        if hashlib.sha256(self.helper.read_bytes()).hexdigest() != helper_sha256 or not os.access(self.helper, os.X_OK):
            raise ValueError("Compiled helper does not match trusted executable")
        self.helper_sha256 = helper_sha256
        self.recipient = require_private_path(recipient, directory=True)
        self.scratch = require_private_path(scratch, directory=True)
        for name in ("recipient-public.pem", "private-key.encrypted.pem", "recipient-metadata.json"):
            require_private_path(self.recipient / name)
        if hashlib.sha256((self.recipient / "recipient-public.pem").read_bytes()).hexdigest() != recipient_sha256:
            raise ValueError("Recipient differs from trusted certificate pin")
        self.pin = recipient_sha256

    def __call__(self, ciphertext):
        """Decrypt one CMS record through the private helper and return authenticated bytes.

        Inputs:
            ciphertext: One bounded encrypted byte record supplied by the archive verifier.
        Outputs:
            bytes: Authenticated plaintext in memory only. Creates/deletes one private ciphertext
                temporary file; helper failures never expose stdout, stderr, passphrase or key data.
        """
        if not isinstance(ciphertext, bytes) or not ciphertext:
            raise ValueError("Nonempty encrypted record required")
        if hashlib.sha256(self.helper.read_bytes()).hexdigest() != self.helper_sha256:
            raise ValueError("Decryption helper changed")
        try:
            # Only ciphertext touches scratch storage; plaintext is consumed through a captured pipe.
            with tempfile.NamedTemporaryFile(dir=self.scratch, suffix=".cms", prefix="record-", mode="wb") as temporary:
                temporary.write(ciphertext)
                temporary.flush()
                result = subprocess.run([str(self.helper), str(self.recipient), temporary.name, self.pin],
                                        capture_output=True, check=True, timeout=60)
            return result.stdout
        except subprocess.TimeoutExpired:
            raise ValueError("Local decryption timed out; authorize the dedicated Keychain item locally") from None
        except subprocess.SubprocessError:
            # In particular, never echo CalledProcessError output which may hold partial sensitive bytes.
            raise ValueError("Authenticated local decryption failed; no plaintext admitted") from None
