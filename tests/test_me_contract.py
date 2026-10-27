"""Exercise the published me grant schema and rendered, non-mutating probes.

Run with the same current unitysvc-core / seller environment used for specs
validation: python -m unittest discover -s tests -v.
"""

import json
import os
import subprocess
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from unitysvc_core.grants import check_claim, parse_exports, parse_options

ME = Path(__file__).resolve().parents[1] / "services" / "specs" / "me"


class MeExportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exports = parse_exports(
            "me", json.loads((ME / "offering.json").read_text())["exports"]
        )

    def claim(self, options, permissions=None):
        check_claim(
            "test",
            "service:me",
            permissions or ["read", "write"],
            parse_options("test", options),
            self.exports,
        )

    def test_resources_are_independent_optional_selectors(self):
        for options in (
            "",
            "profile=research,address.state",
            "intents=travel,needs",
            "preferences=reading,tools",
            "intents=travel&preferences=reading",
        ):
            with self.subTest(options=options):
                self.claim(options)
        for resource in ("intents", "preferences"):
            self.assertEqual(
                self.exports.options["properties"][resource]["default"], []
            )

    def test_named_category_boundaries(self):
        categories = ",".join(f"category-{index}" for index in range(64))
        for resource in ("intents", "preferences"):
            self.claim(f"{resource}={categories}")
            self.claim(f"{resource}=" + "a" * 64)
            for invalid in (
                categories + ",overflow",
                "a" * 65,
                "needs.books",
                "1travel",
                "Travel",
                "a/b",
                "旅行",
                "travel%0A",
                "travel,travel",
                "travel,",
                "*​",
            ):
                with (
                    self.subTest(resource=resource, invalid=invalid),
                    self.assertRaises(ValueError),
                ):
                    self.claim(f"{resource}={invalid}")

    def test_manual_wildcard_is_sole_selector(self):
        # Enrollment/delegation restrictions need issuer context and are enforced
        # by the backend; the published schema handles the selector shape.
        for resource in ("intents", "preferences"):
            self.claim(f"{resource}=*")
            for invalid in ("*,travel", "travel,*", "*,*"):
                with (
                    self.subTest(resource=resource, invalid=invalid),
                    self.assertRaises(ValueError),
                ):
                    self.claim(f"{resource}={invalid}")

    def test_duplicate_and_unknown_options_are_refused(self):
        for options in ("intents=travel&intents=needs", "settings=ai", "intents="):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.claim(options)

    def test_no_invoke_or_whole_resource_write(self):
        with self.assertRaises(ValueError):
            self.claim("intents=travel", ["invoke"])
        self.assertNotIn("POST /intents", self.exports.permissions["write"])
        self.assertNotIn("POST /preferences", self.exports.permissions["write"])


class MeDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.templates = Environment(
            loader=FileSystemLoader(ME), undefined=StrictUndefined
        )

    def render(self, name, local_testing, base_url="http://unused.invalid/me"):
        return self.templates.get_template(name).render(
            local_testing=local_testing, service_base_url=base_url
        )

    def test_local_mode_has_no_upstream(self):
        for name, command in (
            ("connectivity.sh.j2", ["bash"]),
            ("code-example.py.j2", [os.sys.executable]),
        ):
            with self.subTest(name=name):
                result = subprocess.run(
                    command,
                    input=self.render(name, True),
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rendered_python_is_valid(self):
        compile(self.render("code-example.py.j2", False), "code-example.py", "exec")

    def test_connectivity_checks_all_three_wrappers_without_writes(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                resource = self.path.rsplit("/", 1)[-1]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({resource: {}}).encode())

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            script = self.render(
                "connectivity.sh.j2", False, f"http://127.0.0.1:{server.server_port}/me"
            )
            result = subprocess.run(
                ["bash"],
                input=script,
                text=True,
                capture_output=True,
                timeout=20,
                env={**os.environ, "UNITYSVC_API_KEY": "contract-test"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, ["/me/profile", "/me/intents", "/me/preferences"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
