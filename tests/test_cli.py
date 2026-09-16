from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("yxh_cli", ROOT / "yunxiaohe-client" / "scripts" / "yxh.py")
yxh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(yxh)
TOKEN = "yhsk_" + "a" * 43
BASE_PATH = "/client/yunxiaohe/skill/v1/"


class FixtureHandler(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, _format, *_args):
        return

    def _reply(self, status, value=b"", content_type="application/json"):
        body = value if isinstance(value, bytes) else json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def _record(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.calls.append((self.command, self.path, dict(self.headers), body))
        return body

    def do_GET(self):
        self._record()
        if self.path == BASE_PATH + "capabilities":
            self._reply(200, {"interaction": ["structured_task", "worker_control"]})
        elif self.path == BASE_PATH + "state":
            self._reply(200, {"tasks": [{"id": "task-0123456789ab", "pi_id": "pi-0123456789ab",
                                          "status": "completed"}], "workers": [], "agentic_loops": []})
        else:
            self._reply(404, {"error": "not_found"})

    def do_POST(self):
        body = self._record()
        if self.path == BASE_PATH + "tasks":
            self._reply(201, {"id": "task-0123456789ab", "received": json.loads(body)})
        elif self.path == BASE_PATH + "pis/pi-0123456789ab/exports/pdf":
            self._reply(200, b"%PDF-1.4\nsynthetic\n%%EOF\n", "application/pdf")
        else:
            self._reply(404, {"error": "not_found"})


class CLITests(unittest.TestCase):
    def setUp(self):
        FixtureHandler.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "credentials.json"
        self.environment = patch.dict(os.environ, {
            "YXH_API_BASE": f"http://127.0.0.1:{self.server.server_port}{BASE_PATH}",
            "YXH_CONFIG": str(self.config),
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def run_cli(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = yxh.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def login(self):
        with patch.object(yxh.getpass, "getpass", return_value=TOKEN):
            code, output, error = self.run_cli(["login"])
        self.assertEqual((0, ""), (code, error))
        self.assertNotIn(TOKEN, output)
        self.assertTrue(self.config.exists())
        method, path, headers, body = FixtureHandler.calls[-1]
        self.assertEqual(("GET", BASE_PATH + "capabilities"), (method, path))
        self.assertEqual("Bearer " + TOKEN, headers["Authorization"])
        self.assertEqual(b"", body)

    def test_login_bearer_dispatch_wait_export_and_logout(self):
        self.login()

        code, output, error = self.run_cli(["capabilities"])
        self.assertEqual((0, ""), (code, error))
        self.assertIn("structured_task", output)
        self.assertEqual("Bearer " + TOKEN, FixtureHandler.calls[-1][2]["Authorization"])

        code, output, error = self.run_cli([
            "dispatch", "--pi", "pi-0123456789ab", "--title", "Synthetic", "--prompt", "Do work",
            "--acceptance", "Return evidence", "--data-boundary", "Public data only",
        ])
        self.assertEqual((0, ""), (code, error))
        sent = json.loads(FixtureHandler.calls[-1][3])
        self.assertEqual("pi-0123456789ab", sent["pi_id"])
        self.assertEqual("investigator", sent["role_id"])
        self.assertEqual("inherit", sent["loop_template_id"])

        code, output, error = self.run_cli(["wait", "task-0123456789ab", "--timeout", "1", "--interval", "1"])
        self.assertEqual(0, code)
        self.assertIn('"status": "completed"', output)
        self.assertIn('"progress": true', error)

        pdf = Path(self.temp.name) / "result.pdf"
        code, output, error = self.run_cli([
            "export", "--pi", "pi-0123456789ab", "--format", "pdf", "--output", str(pdf),
        ])
        self.assertEqual((0, ""), (code, error))
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))

        code, output, error = self.run_cli(["logout"])
        self.assertEqual((0, ""), (code, error))
        self.assertFalse(self.config.exists())
        self.assertNotEqual(BASE_PATH + "logout", FixtureHandler.calls[-1][1])

    def test_invalid_id_endpoint_and_pdf_fail_closed(self):
        self.login()
        code, _output, error = self.run_cli([
            "talk", "--pi", "../pi-0123456789ab", "--content", "unsafe",
        ])
        self.assertEqual(2, code)
        self.assertIn("Invalid PI ID", error)
        with patch.dict(os.environ, {"YXH_API_BASE": "https://evil.example/client/yunxiaohe/skill/v1/"}):
            code, _output, error = self.run_cli(["capabilities"])
        self.assertEqual(2, code)
        self.assertIn("non-official", error)


if __name__ == "__main__":
    unittest.main()
