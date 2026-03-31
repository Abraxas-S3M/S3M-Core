#!/usr/bin/env python3
"""Tests for S3M Tactical CLI - Phase 4."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from io import StringIO
from unittest.mock import patch, MagicMock
from src.cli.tactical_cli import TacticalCLI


class TestCLIInitialization(unittest.TestCase):
    """Test CLI initialization."""

    def test_default_config(self):
        cli = TacticalCLI()
        self.assertEqual(cli.api_url, "http://localhost:8080")
        self.assertEqual(cli.current_engine, "phi3")
        self.assertEqual(cli.current_domain, "general")
        self.assertEqual(cli.temperature, 0.7)
        self.assertEqual(cli.max_tokens, 512)

    def test_custom_api_url(self):
        cli = TacticalCLI(api_url="http://192.168.1.100:9090")
        self.assertEqual(cli.api_url, "http://192.168.1.100:9090")

    def test_history_starts_empty(self):
        cli = TacticalCLI()
        self.assertEqual(len(cli.history), 0)


class TestCLIEngineCommands(unittest.TestCase):
    """Test engine management commands."""

    def setUp(self):
        self.cli = TacticalCLI()

    def test_set_valid_engine(self):
        self.cli.do_engine("grok")
        self.assertEqual(self.cli.current_engine, "grok")

    def test_set_invalid_engine(self):
        self.cli.do_engine("invalid")
        self.assertEqual(self.cli.current_engine, "phi3")  # unchanged

    def test_set_all_engines(self):
        for eng in ["phi3", "grok", "mistral", "allam"]:
            self.cli.do_engine(eng)
            self.assertEqual(self.cli.current_engine, eng)


class TestCLIConfigCommands(unittest.TestCase):
    """Test configuration commands."""

    def setUp(self):
        self.cli = TacticalCLI()

    def test_set_valid_domain(self):
        self.cli.do_domain("tactical")
        self.assertEqual(self.cli.current_domain, "tactical")

    def test_set_invalid_domain(self):
        self.cli.do_domain("invalid")
        self.assertEqual(self.cli.current_domain, "general")  # unchanged

    def test_set_temperature(self):
        self.cli.do_temp("0.5")
        self.assertEqual(self.cli.temperature, 0.5)

    def test_set_invalid_temperature(self):
        self.cli.do_temp("3.0")
        self.assertEqual(self.cli.temperature, 0.7)  # unchanged

    def test_set_tokens(self):
        self.cli.do_tokens("1024")
        self.assertEqual(self.cli.max_tokens, 1024)

    def test_set_invalid_tokens(self):
        self.cli.do_tokens("abc")
        self.assertEqual(self.cli.max_tokens, 512)  # unchanged


class TestCLIExitCommands(unittest.TestCase):
    """Test exit commands."""

    def setUp(self):
        self.cli = TacticalCLI()

    def test_exit_returns_true(self):
        result = self.cli.do_exit("")
        self.assertTrue(result)

    def test_quit_returns_true(self):
        result = self.cli.do_quit("")
        self.assertTrue(result)

    def test_eof_returns_true(self):
        result = self.cli.do_EOF("")
        self.assertTrue(result)


class TestCLIEmptyLine(unittest.TestCase):
    """Test empty line handling."""

    def test_empty_line_does_nothing(self):
        cli = TacticalCLI()
        result = cli.emptyline()
        self.assertIsNone(result)


class TestCLIOutputMethods(unittest.TestCase):
    """Test output formatting methods."""

    def setUp(self):
        self.cli = TacticalCLI()

    @patch('sys.stdout', new_callable=StringIO)
    def test_print_info(self, mock_stdout):
        self.cli._print_info("test message")
        self.assertIn("test message", mock_stdout.getvalue())

    @patch('sys.stdout', new_callable=StringIO)
    def test_print_error(self, mock_stdout):
        self.cli._print_error("error message")
        self.assertIn("error message", mock_stdout.getvalue())

    @patch('sys.stdout', new_callable=StringIO)
    def test_print_table(self, mock_stdout):
        self.cli._print_table(["Name", "Value"], [["a", "1"], ["b", "2"]])
        output = mock_stdout.getvalue()
        self.assertIn("Name", output)
        self.assertIn("Value", output)


if __name__ == "__main__":
    print("=" * 60)
    print("  S3M Phase 4 CLI Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
