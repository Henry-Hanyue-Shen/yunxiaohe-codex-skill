#!/usr/bin/env python3
"""Local workspace data plane for the YunXiaoHe Codex Skill.

This module never contacts the YunXiaoHe service. It registers explicitly
selected files inside one workspace root, produces portable metadata, and
stages deliverables locally. File contents remain on the device unless the
user separately authorizes Codex to transmit selected content.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys


SCHEMA = "yh.local-workspace.v1"
CONTROL_DIR = ".yxh"
MANIFEST_NAME = "workspace.json"
WORKSPACE_RE = re.compile(r"ws-[0-9a-f]{16}")
OBJECT_RE = re.compile(r"obj-[0-9a-f]{24}")
REFERENCE_RE = re.compile(r"local://(ws-[0-9a-f]{16})/(obj-[0-9a-f]{24})")
TASK_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
DEFAULT_READ_BYTES = 256 * 1024
MAX_READ_BYTES = 8 * 1024 * 1024
BLOCKED_DIRS = {CONTROL_DIR, ".git", ".hg", ".svn"}
BLOCKED_NAMES = {
    ".env", ".npmrc", ".pypirc", "credentials.json", "id_dsa", "id_ecdsa",
    "id_ed25519", "id_rsa", "known_hosts", "netrc", ".netrc",
}
BLOCKED_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}


class WorkspaceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}-{secrets.token_hex(4)}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _is_linklike(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse)
    except FileNotFoundError:
        return False


def _assert_no_link_components(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise WorkspaceError("Path is outside the bound local workspace") from error
    current = root
    if _is_linklike(current):
        raise WorkspaceError("Workspace roots cannot be symlinks, junctions, or reparse points")
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_linklike(current):
            raise WorkspaceError("Symlinks, junctions, and reparse points are not allowed in a local workspace path")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _manifest_path(root: Path) -> Path:
    return root / CONTROL_DIR / MANIFEST_NAME


def _find_root(start: str | None) -> Path:
    candidate = _absolute(Path(start or os.getcwd()))
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        manifest = _manifest_path(current)
        if manifest.is_file():
            _assert_no_link_components(current, manifest)
            return current
    raise WorkspaceError("No local workspace found; run `local_workspace.py init PATH`")


def _validate_manifest(value) -> dict:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise WorkspaceError("Local workspace manifest is invalid")
    if not WORKSPACE_RE.fullmatch(str(value.get("workspace_id", ""))):
        raise WorkspaceError("Local workspace ID is invalid")
    if not isinstance(value.get("entries"), dict) or not isinstance(value.get("outputs"), dict):
        raise WorkspaceError("Local workspace manifest is invalid")
    for object_id, entry in value["entries"].items():
        if not OBJECT_RE.fullmatch(str(object_id)) or not isinstance(entry, dict):
            raise WorkspaceError("Local workspace entry is invalid")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise WorkspaceError("Local workspace contains an unsafe path")
        if any(part in {"", ".", ".."} for part in relative.replace("\\", "/").split("/")):
            raise WorkspaceError("Local workspace contains an unsafe path")
    return value


def _load(root: Path) -> dict:
    try:
        value = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
        raise WorkspaceError("Local workspace manifest cannot be read") from error
    return _validate_manifest(value)


def _save(root: Path, manifest: dict) -> None:
    _atomic_json(_manifest_path(root), _validate_manifest(manifest))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _blocked(relative: Path) -> bool:
    parts = {part.lower() for part in relative.parts}
    name = relative.name.lower()
    return bool(parts & BLOCKED_DIRS or name in BLOCKED_NAMES or relative.suffix.lower() in BLOCKED_SUFFIXES)


def _safe_source(root: Path, value: str) -> tuple[Path, str]:
    raw = Path(value).expanduser()
    target = _absolute(raw if raw.is_absolute() else root / raw)
    _assert_no_link_components(root, target)
    try:
        relative_path = target.relative_to(root)
    except ValueError as error:
        raise WorkspaceError("Path is outside the bound local workspace") from error
    if _blocked(relative_path):
        raise WorkspaceError("Control, VCS, credential, and private-key paths cannot be registered")
    if not target.is_file():
        raise WorkspaceError(f"Local workspace source is not a regular file: {relative_path.as_posix()}")
    return target, relative_path.as_posix()


def _entry_for_ref(manifest: dict, reference: str) -> tuple[str, dict]:
    match = REFERENCE_RE.fullmatch(reference)
    if not match or match.group(1) != manifest["workspace_id"]:
        raise WorkspaceError("Local reference does not belong to this workspace")
    object_id = match.group(2)
    entry = manifest["entries"].get(object_id)
    if not isinstance(entry, dict):
        raise WorkspaceError("Local reference is not registered")
    return object_id, entry


def _reference(manifest: dict, object_id: str) -> str:
    return f"local://{manifest['workspace_id']}/{object_id}"


def _current_file(root: Path, entry: dict, *, verify_hash: bool) -> Path:
    target, relative = _safe_source(root, entry["path"])
    if relative != entry["path"]:
        raise WorkspaceError("Registered path changed unexpectedly")
    details = target.stat()
    if details.st_size != entry.get("bytes"):
        raise WorkspaceError("Registered file changed; run `add` again to approve the new revision")
    if verify_hash and _sha256(target) != entry.get("sha256"):
        raise WorkspaceError("Registered file changed; run `add` again to approve the new revision")
    return target


def command_init(args) -> None:
    root = _absolute(Path(args.path))
    if not root.is_dir():
        raise WorkspaceError("Workspace root must be an existing directory")
    if _is_linklike(root):
        raise WorkspaceError("Workspace roots cannot be symlinks, junctions, or reparse points")
    manifest_path = _manifest_path(root)
    if manifest_path.exists():
        raise WorkspaceError("A local workspace already exists at this root")
    control = root / CONTROL_DIR
    if control.exists() and _is_linklike(control):
        raise WorkspaceError("Existing .yxh path is unsafe")
    (control / "outputs").mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest = {
        "schema": SCHEMA,
        "workspace_id": "ws-" + secrets.token_hex(8),
        "name": args.name or root.name,
        "created_at": _now(),
        "updated_at": _now(),
        "entries": {},
        "outputs": {},
    }
    _save(root, manifest)
    _print({
        "initialized": True,
        "workspace_id": manifest["workspace_id"],
        "name": manifest["name"],
        "root": str(root),
        "file_storage": "local_only",
        "server_quota_used": False,
    })


def command_status(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    usage = shutil.disk_usage(root)
    registered = sum(int(item.get("bytes", 0)) for item in manifest["entries"].values())
    output_count = sum(len(items) for items in manifest["outputs"].values() if isinstance(items, list))
    _print({
        "workspace_id": manifest["workspace_id"],
        "name": manifest["name"],
        "root": str(root),
        "registered_files": len(manifest["entries"]),
        "registered_bytes": registered,
        "staged_outputs": output_count,
        "disk_free_bytes": usage.free,
        "file_storage": "local_only",
        "server_quota_used": False,
        "remote_worker_file_access": False,
    })


def command_add(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    results = []
    for value in args.paths:
        target, relative = _safe_source(root, value)
        details = target.stat()
        existing = next(((key, item) for key, item in manifest["entries"].items()
                         if item.get("path") == relative), None)
        object_id = existing[0] if existing else "obj-" + secrets.token_hex(12)
        mime, _encoding = mimetypes.guess_type(target.name)
        manifest["entries"][object_id] = {
            "path": relative,
            "name": target.name,
            "bytes": details.st_size,
            "mtime_ns": details.st_mtime_ns,
            "sha256": _sha256(target),
            "mime": mime or "application/octet-stream",
            "access": args.access,
            "updated_at": _now(),
        }
        results.append({
            "reference": _reference(manifest, object_id),
            "path": relative,
            "bytes": details.st_size,
            "sha256": manifest["entries"][object_id]["sha256"],
            "access": args.access,
        })
    manifest["updated_at"] = _now()
    _save(root, manifest)
    _print({"registered": results, "file_contents_uploaded": False})


def command_list(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    results = []
    for object_id, entry in sorted(manifest["entries"].items(), key=lambda item: item[1]["path"]):
        try:
            target, relative = _safe_source(root, entry["path"])
            details = target.stat()
            status = "present" if (relative == entry["path"] and details.st_size == entry["bytes"]) else "changed"
        except WorkspaceError:
            status = "missing_or_unsafe"
        results.append({
            "reference": _reference(manifest, object_id),
            "path": entry["path"],
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
            "access": entry["access"],
            "status": status,
        })
    _print({"workspace_id": manifest["workspace_id"], "files": results})


def command_verify(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    results = []
    valid = True
    for object_id, entry in sorted(manifest["entries"].items(), key=lambda item: item[1]["path"]):
        try:
            _current_file(root, entry, verify_hash=True)
            status = "verified"
        except WorkspaceError:
            valid = False
            status = "changed_missing_or_unsafe"
        results.append({"reference": _reference(manifest, object_id), "path": entry["path"], "status": status})
    _print({"verified": valid, "files": results})
    if not valid:
        raise WorkspaceError("One or more registered files no longer match the approved revision")


def command_read(args) -> None:
    if args.max_bytes < 4 or args.max_bytes > MAX_READ_BYTES or args.offset < 0:
        raise WorkspaceError(f"Read range must be at least 4 and no larger than {MAX_READ_BYTES} bytes")
    root = _find_root(args.workspace)
    manifest = _load(root)
    _object_id, entry = _entry_for_ref(manifest, args.reference)
    if entry.get("access") != "full-text":
        raise WorkspaceError("This file is metadata-only; re-run `add --access full-text` with user authorization")
    target = _current_file(root, entry, verify_hash=True)
    with target.open("rb") as stream:
        stream.seek(args.offset)
        window = stream.read(args.max_bytes + 4)
    raw = window[:args.max_bytes]
    decoder = "utf-8-sig" if args.offset == 0 else "utf-8"
    while True:
        try:
            content = raw.decode(decoder)
            break
        except UnicodeDecodeError as error:
            trailing_partial = error.end == len(raw) and error.start >= max(0, len(raw) - 4)
            if trailing_partial and error.start > 0:
                raw = raw[:error.start]
                continue
            raise WorkspaceError(
                "Full-text reads require UTF-8 and offsets returned by the previous read; "
                "use metadata mode for binary files"
            ) from error
    next_offset = args.offset + len(raw)
    truncated = next_offset < entry["bytes"]
    _print({
        "reference": args.reference,
        "path": entry["path"],
        "sha256": entry["sha256"],
        "offset": args.offset,
        "bytes_read": len(raw),
        "next_offset": next_offset if truncated else None,
        "truncated": truncated,
        "content": content,
        "file_contents_uploaded": False,
    })


def command_remove(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    object_id, entry = _entry_for_ref(manifest, args.reference)
    del manifest["entries"][object_id]
    manifest["updated_at"] = _now()
    _save(root, manifest)
    _print({"reference_removed": args.reference, "path": entry["path"], "file_deleted": False})


def command_context(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    if args.references:
        selected = [_entry_for_ref(manifest, reference) for reference in args.references]
    else:
        selected = list(manifest["entries"].items())
    files = []
    for object_id, entry in selected:
        _current_file(root, entry, verify_hash=True)
        files.append({
            "reference": _reference(manifest, object_id),
            "name": entry["name"],
            "relative_path": entry["path"],
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
            "mime": entry["mime"],
            "access": entry["access"],
        })
    _print({
        "schema": "yh.local-context.v1",
        "workspace_id": manifest["workspace_id"],
        "workspace_name": manifest["name"],
        "files": files,
        "absolute_paths_included": False,
        "file_contents_included": False,
        "remote_worker_file_access": False,
    })


def command_stage_output(args) -> None:
    if not TASK_LABEL_RE.fullmatch(args.task):
        raise WorkspaceError("Task label must use only letters, numbers, dot, underscore, and hyphen")
    root = _find_root(args.workspace)
    manifest = _load(root)
    source, _relative = _safe_source(root, args.source)
    name = args.name or source.name
    if name != Path(name).name or name in {"", ".", ".."}:
        raise WorkspaceError("Output name must be one file name")
    destination_dir = root / CONTROL_DIR / "outputs" / args.task
    destination_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = destination_dir / name
    _assert_no_link_components(root, destination)
    if destination.exists() and not args.force:
        raise WorkspaceError("Staged output already exists; pass --force to replace it")
    temporary = destination.with_name(destination.name + f".tmp-{os.getpid()}-{secrets.token_hex(4)}")
    try:
        with source.open("rb") as incoming, temporary.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    record = {
        "name": name,
        "path": destination.relative_to(root).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "staged_at": _now(),
    }
    items = manifest["outputs"].setdefault(args.task, [])
    items[:] = [item for item in items if item.get("name") != name]
    items.append(record)
    manifest["updated_at"] = _now()
    _save(root, manifest)
    _print({"task": args.task, "output": record, "stored": "local_only", "server_quota_used": False})


def command_list_outputs(args) -> None:
    root = _find_root(args.workspace)
    manifest = _load(root)
    outputs = manifest["outputs"]
    if args.task:
        outputs = {args.task: outputs.get(args.task, [])}
    _print({"workspace_id": manifest["workspace_id"], "outputs": outputs, "stored": "local_only"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a device-local YunXiaoHe workspace")
    parser.add_argument("--workspace", help="workspace root or a path below it; defaults to the current directory")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="bind an existing directory as a local workspace")
    init.add_argument("path")
    init.add_argument("--name")
    init.set_defaults(func=command_init)

    status = commands.add_parser("status", help="show local capacity and workspace status")
    status.set_defaults(func=command_status)

    add = commands.add_parser("add", help="register approved local files without uploading them")
    add.add_argument("paths", nargs="+")
    add.add_argument("--access", choices=("metadata", "full-text"), default="metadata")
    add.set_defaults(func=command_add)

    listing = commands.add_parser("list", help="list registered files and lightweight status")
    listing.set_defaults(func=command_list)

    verify = commands.add_parser("verify", help="rehash every registered file")
    verify.set_defaults(func=command_verify)

    read = commands.add_parser("read", help="read an approved UTF-8 file through its opaque local reference")
    read.add_argument("reference")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--max-bytes", type=int, default=DEFAULT_READ_BYTES)
    read.set_defaults(func=command_read)

    remove = commands.add_parser("remove", help="remove a reference without deleting its file")
    remove.add_argument("reference")
    remove.set_defaults(func=command_remove)

    context = commands.add_parser("context", help="emit portable metadata without absolute paths or file contents")
    context.add_argument("references", nargs="*")
    context.set_defaults(func=command_context)

    stage = commands.add_parser("stage-output", help="copy a workspace file into a task-scoped local output area")
    stage.add_argument("--task", required=True)
    stage.add_argument("--source", required=True)
    stage.add_argument("--name")
    stage.add_argument("--force", action="store_true")
    stage.set_defaults(func=command_stage_output)

    outputs = commands.add_parser("list-outputs", help="list local deliverables")
    outputs.add_argument("--task")
    outputs.set_defaults(func=command_list_outputs)
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        args.func(args)
        return 0
    except (WorkspaceError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted; no local files were deleted and no remote action was sent", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
