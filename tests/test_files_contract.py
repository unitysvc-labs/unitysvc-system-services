"""Exercise the published home and storage grant schemas and rendered probes.

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

SPECS = Path(__file__).resolve().parents[1] / "services" / "specs"


def exports(name):
    return parse_exports(
        name, json.loads((SPECS / name / "offering.json").read_text())["exports"]
    )


def claim(name, options, permissions=("read", "write")):
    check_claim(
        "test",
        f"service:{name}",
        list(permissions),
        parse_options("test", options),
        exports(name),
    )


class FilesExportsTests(unittest.TestCase):
    def test_read_write_and_no_invoke(self):
        for name in ("home", "storage"):
            with self.subTest(name=name):
                self.assertEqual(exports(name).permission_names, ("read", "write"))
                with self.assertRaises(ValueError):
                    claim(name, "", ["invoke"])

    def test_home_folders(self):
        folders = ",".join(f"f{index}/" for index in range(32))
        for options in (
            "",
            "path=inputs/",
            "path=inputs/datasets/,projects/project-x/",
            "path=a.b/c_d-e/",
            "path=" + "x" * 255 + "/",
            "path=*",
            f"path={folders}",
        ):
            with self.subTest(options=options):
                claim("home", options)
        self.assertEqual(exports("home").options["properties"]["path"]["default"], [])

    def test_home_refuses_malformed_folders(self):
        for invalid in (
            "inputs",
            "/inputs/",
            "../inputs/",
            "inputs/../x/",
            "./inputs/",
            ".hidden/",
            "a//",
            "a b/",
            "a\\b/",
            "*,inputs/",
            "inputs/,inputs/",
            ",".join(f"f{index}/" for index in range(33)),
            "x" * 512 + "/",
            "inputs/a..b/",
            "x" * 256 + "/",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                claim("home", f"path={invalid}")

    def test_no_bucket_or_folder_selectors(self):
        for name, options in (
            ("home", "bucket=user-files"),
            ("storage", "path=results/"),
            ("storage", "bucket=user-files"),
            ("storage", "enrollment=AB3D9K"),
        ):
            with self.subTest(name=name, options=options), self.assertRaises(ValueError):
                claim(name, options)

    def test_listings_are_private(self):
        for name in ("home", "storage"):
            listing = json.loads((SPECS / name / "listing.json").read_text())
            self.assertEqual(listing["service_options"]["default_visibility"], "private")


class FilesDocumentsTests(unittest.TestCase):
    def render(self, name, template, local_testing, base_url="http://unused.invalid"):
        templates = Environment(
            loader=FileSystemLoader(SPECS / name), undefined=StrictUndefined
        )
        return templates.get_template(template).render(
            local_testing=local_testing, service_base_url=base_url
        )

    def run_bash(self, script):
        return subprocess.run(
            ["bash"],
            input=script,
            text=True,
            capture_output=True,
            timeout=20,
            env={**os.environ, "UNITYSVC_API_KEY": "contract-test"},
        )

    def test_local_mode_has_no_upstream(self):
        for name in ("home", "storage"):
            with self.subTest(name=name):
                result = self.run_bash(self.render(name, "connectivity.sh.j2", True))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rendered_python_is_valid(self):
        for name in ("home", "storage"):
            compile(
                self.render(name, "code-example.py.j2", False), "code-example.py", "exec"
            )

    def test_connectivity_accepts_only_the_services_own_answers(self):
        answer = {}
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                calls.append((self.path, json.loads(body)))
                status, payload = answer["value"]
                self.send_response(status)
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        listing = {"path": "", "files": [], "folders": [], "next_cursor": None}
        cases = (
            ("home", 200, listing, True),
            ("home", 403, {"error": "no service:home grant with read"}, True),
            ("home", 400, {"error": "X-UnitySVC-Enrollment header is required"}, False),
            ("home", 502, {"error": "bad gateway"}, False),
            ("storage", 200, listing, True),
            ("storage", 403, {"error": "no service:storage grant with read"}, True),
            ("storage", 400, {"error": "X-UnitySVC-Enrollment header is required"}, True),
            ("storage", 403, {"error": "no service:home grant"}, False),
        )
        try:
            for name, status, payload, ok in cases:
                with self.subTest(name=name, status=status, payload=payload):
                    answer["value"] = (status, payload)
                    calls.clear()
                    result = self.run_bash(
                        self.render(name, "connectivity.sh.j2", False, f"{base}/{name}")
                    )
                    self.assertEqual(result.returncode == 0, ok, result.stderr)
                    self.assertEqual(calls, [(f"/{name}/list", {"path": ""})])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
