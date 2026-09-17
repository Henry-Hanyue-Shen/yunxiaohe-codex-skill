from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "yxh_local_workspace",
    ROOT / "yunxiaohe-client" / "scripts" / "local_workspace.py",
)
local = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local)


class LocalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = local.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def init(self):
        code, output, error = self.run_cli(["init", str(self.root), "--name", "Test Workspace"])
        self.assertEqual((0, ""), (code, error))
        value = json.loads(output)
        self.assertEqual("local_only", value["file_storage"])
        return value

    def test_metadata_then_full_text_read_and_portable_context(self):
        initialized = self.init()
        source = self.root / "notes.md"
        source.write_bytes("alpha βeta\n".encode("utf-8"))

        code, output, error = self.run_cli([
            "--workspace", str(self.root), "add", "notes.md", "--access", "metadata",
        ])
        self.assertEqual((0, ""), (code, error))
        first = json.loads(output)["registered"][0]
        reference = first["reference"]
        self.assertTrue(reference.startswith("local://" + initialized["workspace_id"] + "/"))

        code, _output, error = self.run_cli([
            "--workspace", str(self.root), "read", reference,
        ])
        self.assertEqual(2, code)
        self.assertIn("metadata-only", error)

        code, output, error = self.run_cli([
            "--workspace", str(self.root), "add", "notes.md", "--access", "full-text",
        ])
        self.assertEqual((0, ""), (code, error))
        second = json.loads(output)["registered"][0]
        self.assertEqual(reference, second["reference"])

        code, output, error = self.run_cli([
            "--workspace", str(self.root), "read", reference,
        ])
        self.assertEqual((0, ""), (code, error))
        self.assertEqual("alpha βeta\n", json.loads(output)["content"])

        code, output, error = self.run_cli([
            "--workspace", str(self.root), "read", reference, "--max-bytes", "7",
        ])
        self.assertEqual((0, ""), (code, error))
        first_chunk = json.loads(output)
        self.assertTrue(first_chunk["truncated"])
        code, output, error = self.run_cli([
            "--workspace", str(self.root), "read", reference,
            "--offset", str(first_chunk["next_offset"]), "--max-bytes", "7",
        ])
        self.assertEqual((0, ""), (code, error))
        self.assertEqual("alpha βeta\n", first_chunk["content"] + json.loads(output)["content"])

        code, output, error = self.run_cli([
            "--workspace", str(self.root), "context", reference,
        ])
        self.assertEqual((0, ""), (code, error))
        context = json.loads(output)
        self.assertFalse(context["file_contents_included"])
        self.assertFalse(context["absolute_paths_included"])
        self.assertNotIn(str(self.root), output)

        manifest_raw = (self.root / ".yxh" / "workspace.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), manifest_raw)

    def test_changed_file_fails_closed_until_reapproved(self):
        self.init()
        source = self.root / "data.txt"
        source.write_text("version one", encoding="utf-8")
        code, output, error = self.run_cli([
            "--workspace", str(self.root), "add", "data.txt", "--access", "full-text",
        ])
        self.assertEqual((0, ""), (code, error))
        reference = json.loads(output)["registered"][0]["reference"]

        source.write_text("version two is different", encoding="utf-8")
        code, _output, error = self.run_cli([
            "--workspace", str(self.root), "verify",
        ])
        self.assertEqual(2, code)
        self.assertIn("no longer match", error)
        code, _output, error = self.run_cli([
            "--workspace", str(self.root), "read", reference,
        ])
        self.assertEqual(2, code)
        self.assertIn("changed", error)

        code, output, error = self.run_cli([
            "--workspace", str(self.root), "add", "data.txt", "--access", "full-text",
        ])
        self.assertEqual((0, ""), (code, error))
        self.assertEqual(reference, json.loads(output)["registered"][0]["reference"])

    def test_scope_secret_guards_and_reference_removal(self):
        self.init()
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        code, _output, error = self.run_cli([
            "--workspace", str(self.root), "add", str(outside),
        ])
        self.assertEqual(2, code)
        self.assertIn("outside", error)

        secret = self.root / ".env"
        secret.write_text("TOKEN=secret", encoding="utf-8")
        code, _output, error = self.run_cli([
            "--workspace", str(self.root), "add", ".env",
        ])
        self.assertEqual(2, code)
        self.assertIn("credential", error)

        source = self.root / "keep.txt"
        source.write_text("keep me", encoding="utf-8")
        code, output, error = self.run_cli([
            "--workspace", str(self.root), "add", "keep.txt",
        ])
        self.assertEqual((0, ""), (code, error))
        reference = json.loads(output)["registered"][0]["reference"]
        code, output, error = self.run_cli([
            "--workspace", str(self.root), "remove", reference,
        ])
        self.assertEqual((0, ""), (code, error))
        self.assertFalse(json.loads(output)["file_deleted"])
        self.assertTrue(source.exists())

    def test_stage_output_is_local_atomic_and_non_overwriting(self):
        self.init()
        source = self.root / "report.md"
        source.write_text("# Result\n", encoding="utf-8")
        arguments = [
            "--workspace", str(self.root), "stage-output",
            "--task", "task-local-001", "--source", "report.md",
        ]
        code, output, error = self.run_cli(arguments)
        self.assertEqual((0, ""), (code, error))
        value = json.loads(output)
        self.assertEqual("local_only", value["stored"])
        staged = self.root / value["output"]["path"]
        self.assertEqual(source.read_bytes(), staged.read_bytes())

        code, _output, error = self.run_cli(arguments)
        self.assertEqual(2, code)
        self.assertIn("already exists", error)
        code, output, error = self.run_cli(arguments + ["--force"])
        self.assertEqual((0, ""), (code, error))

    @unittest.skipIf(os.name == "nt", "ordinary Windows users may not have symlink permission")
    def test_symlink_is_rejected(self):
        self.init()
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "linked.txt"
        link.symlink_to(outside)
        code, _output, error = self.run_cli([
            "--workspace", str(self.root), "add", "linked.txt",
        ])
        self.assertEqual(2, code)
        self.assertIn("Symlinks", error)


if __name__ == "__main__":
    unittest.main()
