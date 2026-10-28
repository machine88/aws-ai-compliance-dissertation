"""Portable subprocess-boundary tests; never access a real Keychain or user private key."""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.keychain_decryption import MacKeychainDecryptor


class KeychainBridgeTests(unittest.TestCase):
    """Check trusted helper binding, private scratch cleanup and secret-safe failures."""

    def setUp(self):
        """Create private dummy helper/recipient files and a synthetic certificate pin.

        Inputs:
            No external input; temporary dummy byte strings only.
        Outputs:
            None: Stores private fixture paths; no real executable, key or Keychain item is used.
        """
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.helper = self.root/'dummy-helper'
        self.helper.write_bytes(b'synthetic-helper-not-executed')
        self.helper.chmod(0o700)
        self.helper_hash = hashlib.sha256(self.helper.read_bytes()).hexdigest()
        self.recipient, self.scratch = self.root/'recipient', self.root/'scratch'
        self.recipient.mkdir(mode=0o700)
        self.scratch.mkdir(mode=0o700)
        for name in ('recipient-public.pem','private-key.encrypted.pem','recipient-metadata.json'):
            path=self.recipient/name
            path.write_bytes(b'synthetic-fixture-not-real-key-material')
            path.chmod(0o600)
        self.pin=hashlib.sha256((self.recipient/'recipient-public.pem').read_bytes()).hexdigest()

    def bridge(self):
        """Construct the bridge under a simulated macOS platform without executing the helper.

        Inputs:
            Current private test fixture and its independent expected fingerprints.
        Outputs:
            MacKeychainDecryptor: Validated callback; no subprocess or Keychain access yet.
        """
        with patch('research.keychain_decryption.platform.system',return_value='Darwin'):
            return MacKeychainDecryptor(self.helper,self.helper_hash,self.recipient,self.pin,self.scratch)

    def fake_run(self, args, capture_output, check, timeout):
        """Inspect the private ciphertext temporary file instead of running a native helper.

        Inputs:
            args: Helper argv containing public paths and certificate fingerprint only.
            capture_output: Must be true to keep plaintext out of terminal output.
            check: Must be true to reject cryptographic helper failure.
            timeout: Must bound the native call duration.
        Outputs:
            CompletedProcess: Synthetic authenticated plaintext bytes; no actual key operation.
        """
        path=Path(args[2])
        self.assertEqual(path.read_bytes(),b'synthetic-ciphertext')
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertTrue(capture_output and check)
        self.assertEqual(timeout,60)
        self.assertEqual(args[-1],self.pin)
        return subprocess.CompletedProcess(args,0,stdout=b'{"synthetic":true}',stderr=b'')

    def test_plaintext_stays_in_captured_pipe_and_scratch_is_removed(self):
        """Return helper bytes without writing a decrypted file or leaking argv secrets.

        Inputs:
            Dummy ciphertext and a subprocess stub that validates the private temporary copy.
        Outputs:
            None: Asserts in-memory return and an empty scratch directory after completion.
        """
        bridge=self.bridge()
        with patch('research.keychain_decryption.subprocess.run',side_effect=self.fake_run):
            self.assertEqual(bridge(b'synthetic-ciphertext'),b'{"synthetic":true}')
        self.assertEqual(list(self.scratch.iterdir()),[])

    def test_failed_or_timed_out_helper_never_exposes_captured_output(self):
        """Suppress partial helper data and clean ciphertext scratch on every subprocess error.

        Inputs:
            Nonzero-exit and timeout exceptions containing synthetic sensitive-output markers.
        Outputs:
            None: Asserts generic failures exclude those markers and temporary files are gone.
        """
        bridge=self.bridge()
        errors=[subprocess.CalledProcessError(1,['helper'],output=b'private-marker',stderr=b'private-marker'),
                subprocess.TimeoutExpired(['helper'],60,output=b'private-marker',stderr=b'private-marker')]
        for error in errors:
            with patch('research.keychain_decryption.subprocess.run',side_effect=error), self.assertRaises(ValueError) as caught:
                bridge(b'synthetic-ciphertext')
            self.assertNotIn('private-marker',str(caught.exception))
            self.assertEqual(list(self.scratch.iterdir()),[])

    def test_changed_helper_rejected_before_key_access(self):
        """Detect an executable changed after construction rather than trusting its path alone.

        Inputs:
            Validated dummy helper modified before a record is submitted.
        Outputs:
            None: Asserts failure without invoking the subprocess.
        """
        bridge=self.bridge()
        self.helper.write_bytes(b'changed')
        with patch('research.keychain_decryption.subprocess.run') as runner,self.assertRaises(ValueError):
            bridge(b'synthetic-ciphertext')
        runner.assert_not_called()

    def test_platform_recipient_and_private_storage_guards(self):
        """Reject unsupported hosts, recipient substitution and broadly readable recipient files.

        Inputs:
            Dummy fixture with independently broken platform, pin and permission boundaries.
        Outputs:
            None: Asserts constructor rejection without real Keychain access.
        """
        with patch('research.keychain_decryption.platform.system',return_value='Linux'),self.assertRaises(ValueError):
            MacKeychainDecryptor(self.helper,self.helper_hash,self.recipient,self.pin,self.scratch)
        with patch('research.keychain_decryption.platform.system',return_value='Darwin'),self.assertRaises(ValueError):
            MacKeychainDecryptor(self.helper,self.helper_hash,self.recipient,'0'*64,self.scratch)
        (self.recipient/'private-key.encrypted.pem').chmod(0o644)
        with self.assertRaises(ValueError):
            self.bridge()

    def test_symlink_and_empty_input_are_rejected(self):
        """Keep linked files and empty ciphertext out of the native boundary.

        Inputs:
            A valid callback receiving empty input, then a symlinked recipient certificate.
        Outputs:
            None: Asserts rejection with no helper execution or scratch leftovers.
        """
        bridge=self.bridge()
        with self.assertRaises(ValueError):
            bridge(b'')
        certificate=self.recipient/'recipient-public.pem'
        certificate.unlink()
        certificate.symlink_to(self.helper)
        with self.assertRaises(ValueError):
            self.bridge()


if __name__=='__main__':
    unittest.main()
