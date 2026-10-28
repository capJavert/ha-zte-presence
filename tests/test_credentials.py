"""Credential lookup tests: python3 -m unittest discover tests"""

import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

CONST = Path(__file__).resolve().parent.parent / "custom_components" / "zte_presence" / "const.py"
spec = importlib.util.spec_from_file_location("zte_const", CONST)
const = importlib.util.module_from_spec(spec)
sys.modules["zte_const"] = const
spec.loader.exec_module(const)

ENTRIES = (
    '{"192.168.0.13": {"username": "user", "password": "pw,with\\"quote"}, '
    '"http://192.168.0.22": {"username": "admin", "password": "other"}}'
)


def credentials(url, raw=ENTRIES, shared=False):
    env = {"ZTE_CREDENTIALS": raw} if raw is not None else {}
    if shared:
        env |= {"ZTE_USERNAME": "shared", "ZTE_PASSWORD": "shared-pw"}
    with patch.dict(os.environ, env, clear=True):
        return const.credentials_from_env(url)


class CredentialsTest(unittest.TestCase):
    def test_matches_host_of_url(self):
        self.assertEqual(credentials("http://192.168.0.13"), ("user", 'pw,with"quote'))
        self.assertEqual(credentials("https://192.168.0.22:8443/"), ("admin", "other"))

    def test_shared_login(self):
        self.assertEqual(credentials("http://192.168.0.99", raw=None, shared=True), ("shared", "shared-pw"))
        # A ZTE_CREDENTIALS entry wins, other units fall back to the shared login
        self.assertEqual(credentials("http://192.168.0.22", shared=True), ("admin", "other"))
        self.assertEqual(credentials("http://192.168.0.99", shared=True), ("shared", "shared-pw"))

    def test_unknown_host_or_unset(self):
        self.assertIsNone(credentials("http://192.168.0.99"))
        self.assertIsNone(credentials("http://192.168.0.13", raw=None))

    def test_invalid(self):
        for raw in (
            "not json",
            '[["192.168.0.13", "user", "pw"]]',
            '{"192.168.0.13": ["user", "pw"]}',
            '{"192.168.0.13": {"username": "user"}}',
            '{"192.168.0.13": {"username": "user", "password": ""}}',
        ):
            with self.assertRaises(const.CredentialsError) as caught:
                credentials("http://192.168.0.13", raw=raw)
            self.assertNotIn("pw", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
