"""Exercise the published ai grant schema: invoke plus one service option.

Run with the same current unitysvc-core environment used for specs
validation: python -m unittest discover -s tests -v.
"""

import json
import unittest
from pathlib import Path

from unitysvc_core.grants import check_claim, parse_exports, parse_options

AI = Path(__file__).resolve().parents[1] / "services" / "specs" / "ai"


class AiExportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exports = parse_exports(
            "ai", json.loads((AI / "offering.json").read_text())["exports"]
        )

    def claim(self, options, permissions=None):
        check_claim(
            "test",
            "service:ai",
            permissions or ["invoke"],
            parse_options("test", options),
            self.exports,
        )

    def test_ai_keeps_the_implicit_invoke(self):
        # No declared permissions: service:* and service:ai invoke still reach it.
        self.assertEqual(self.exports.permission_names, ("invoke",))
        self.claim("")
        for permissions in (["read"], ["write"], ["invoke", "read"]):
            with self.subTest(permissions=permissions):
                with self.assertRaises(ValueError):
                    self.claim("", permissions)

    def test_service_names_a_catalog_service(self):
        for service in (
            "labs/llm-premium",
            "openai/gpt-5",
            "Qwen/Qwen2.5-Coder-7B-Instruct",
            "claude-opus-4-7@byok",
        ):
            with self.subTest(service=service):
                self.claim(f"service={service}")

    def test_service_refuses_aliases_enrollments_and_ai_itself(self):
        for service in ("a/my-ai", "e/AB3D9K", "b/everyone", "p/llm", "ai", "ai/chat"):
            with self.subTest(service=service):
                with self.assertRaises(ValueError):
                    self.claim(f"service={service}")

    def test_service_is_the_only_option(self):
        with self.assertRaises(ValueError):
            self.claim("model=premium")


if __name__ == "__main__":
    unittest.main()
