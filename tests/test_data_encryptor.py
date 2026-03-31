#!/usr/bin/env python3
"""Unit tests for DataEncryptor."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.crypto.data_encryptor import DataEncryptor


class TestDataEncryptor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.encryptor = DataEncryptor(keys_dir=str(Path(self.tmp.name) / "keys"))
        self.encryptor.generate_key("default")

    def test_generate_key_creates_file(self):
        key_id = self.encryptor.generate_key("alpha")
        key_file = Path(self.tmp.name) / "keys" / f"{key_id}.key"
        self.assertTrue(key_file.exists())

    def test_encrypt_data_decrypt_data_round_trip(self):
        payload = b"tactical payload 123"
        encrypted = self.encryptor.encrypt_data(payload, key_id="default")
        self.assertNotEqual(encrypted, payload)
        decrypted = self.encryptor.decrypt_data(encrypted, key_id="default")
        self.assertEqual(decrypted, payload)

    def test_encrypt_file_creates_enc_file(self):
        src = Path(self.tmp.name) / "sample.bin"
        src.write_bytes(b"mission data")
        out = self.encryptor.encrypt_file(str(src), key_id="default")
        self.assertTrue(Path(out).exists())
        self.assertTrue(out.endswith(".enc"))

    def test_decrypt_file_restores_original(self):
        src = Path(self.tmp.name) / "sample2.bin"
        original = b"classified-ish local test payload"
        src.write_bytes(original)
        enc = self.encryptor.encrypt_file(str(src), key_id="default")
        src.unlink()  # ensure decrypt recreates output from ciphertext
        dec = self.encryptor.decrypt_file(enc, key_id="default")
        self.assertTrue(Path(dec).exists())
        self.assertEqual(Path(dec).read_bytes(), original)

    def test_verify_file_integrity_consistent(self):
        src = Path(self.tmp.name) / "digest.txt"
        src.write_text("abc123", encoding="utf-8")
        h1 = self.encryptor.verify_file_integrity(str(src))
        h2 = self.encryptor.verify_file_integrity(str(src))
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_load_key_reads_generated_key(self):
        self.encryptor.generate_key("bravo")
        key = self.encryptor.load_key("bravo")
        self.assertIsInstance(key, bytes)
        self.assertEqual(len(key), 32)


if __name__ == "__main__":
    unittest.main(verbosity=2)
