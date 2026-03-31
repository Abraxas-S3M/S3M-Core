#!/usr/bin/env python3
"""Unit tests for ClassificationBanner."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.crypto.classification_banner import ClassificationBanner


class TestClassificationBanner(unittest.TestCase):
    def test_get_level_returns_configured_level(self):
        banner = ClassificationBanner(level="SECRET")
        self.assertEqual(banner.get_level(), "SECRET")

    def test_set_level_rejects_invalid_levels(self):
        banner = ClassificationBanner()
        with self.assertRaises(ValueError):
            banner.set_level("INVALID")

    def test_get_banner_html_returns_string_with_level(self):
        banner = ClassificationBanner(level="UNCLASSIFIED - FOUO")
        html = banner.get_banner_html()
        self.assertIn("<div", html)
        self.assertIn("UNCLASSIFIED - FOUO", html)

    def test_validate_response_checks_for_classification_field(self):
        self.assertTrue(ClassificationBanner.validate_response({"classification": "SECRET"}))
        self.assertFalse(ClassificationBanner.validate_response({"value": 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
