#!/usr/bin/env python3
"""Dependency-free CLI for the public YunXiaoHe Skill API.

The customer-managed API key is accepted only by an interactive, no-echo
prompt and is never printed by this CLI.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


OFFICIAL_BASE = "https://yh-intel.cn/client/yunxiaohe/skill/v1/"
TOKEN_RE = re.compile(r"yhsk_[A-Za-z0-9_-]{43}")
PI_RE = re.compile(r"pi-[0-9a-f]{12}")
TASK_RE = re.compile(r"task-[0-9a-f]{12}")
MESSAGE_RE = re.compile(r"msg-[0-9a-f]{12}")
WORKER_RE = re.compile(r"worker-[0-9a-f]{12}")
LOOP_RE = re.compile(r"loop-[0-9a-f]{12}")
MAX_RESPONSE = 64 * 1024 * 1024
TERMINAL_OK = {"completed", "done", "succeeded"}
TERMINAL_BAD = {"failed", "error", "cancelled", "canceled", "aborted"}


class CLIError(RuntimeError):
    pass


class APIError(CLIError):
    def __init__(self, status: int, message: str):
        super().__init__(f"YunXiaoHe API returned HTTP {status}: {message}")
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _validate_base(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    path = "/client/yunxiaohe/skill/v1/"
    official = parsed.scheme == "https" and parsed.hostname == "yh-intel.cn" and parsed.port in (None, 443)
    local_test = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if (not official and not local_test) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CLIError("Refusing a non-official YunXiaoHe endpoint")
    if parsed.path != path:
        raise CLIError("Unexpected YunXiaoHe API path")
    return value


def _api_base() -> str:
    return _validate_base(os.environ.get("YXH_API_BASE", OFFICIAL_BASE))


def _config_path() -> Path:
    override = os.environ.get("YXH_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "YH Intelligence" / "YunXiaoHe Skill" / "credentials.json"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "yh-intelligence" / "yunxiaohe-skill" / "credentials.json"


if os.name == "nt":
    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi_protect(raw: bytes) -> bytes:
    if os.name != "nt":
        raise CLIError("DPAPI is available only on Windows")
    buffer = ctypes.create_string_buffer(raw)
    incoming = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(ctypes.byref(incoming), "YunXiaoHe Skill API key", None, None, None,
                                    0x1, ctypes.byref(outgoing)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel32.LocalFree(outgoing.pbData)


def _dpapi_unprotect(raw: bytes) -> bytes:
    if os.name != "nt":
        raise CLIError("DPAPI is available only on Windows")
    buffer = ctypes.create_string_buffer(raw)
    incoming = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None,
                                      0x1, ctypes.byref(outgoing)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel32.LocalFree(outgoing.pbData)


def _protect_token(token: str) -> str:
    raw = token.encode("ascii")
    if os.name == "nt":
        raw = _dpapi_protect(raw)
        prefix = "dpapi:"
    else:
        prefix = "file0600:"
    return prefix + base64.urlsafe_b64encode(raw).decode("ascii")


def _unprotect_token(value: str) -> str:
    if not isinstance(value, str) or ":" not in value:
        raise CLIError("Credential file is invalid; run login again")
    prefix, encoded = value.split(":", 1)
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except (ValueError, UnicodeError) as error:
        raise CLIError("Credential file is invalid; run login again") from error
    if prefix == "dpapi" and os.name == "nt":
        raw = _dpapi_unprotect(raw)
    elif prefix != "file0600" or os.name == "nt":
        raise CLIError("Credential file belongs to a different platform; run login again")
    try:
        token = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise CLIError("Credential file is invalid; run login again") from error
    if not TOKEN_RE.fullmatch(token):
        raise CLIError("Credential file is invalid; run login again")
    return token


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
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


def _save_api_key(token: str) -> dict:
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise CLIError("API key format is invalid")
    config = {
        "schema": "yh.skill-credential.v2",
        "api_base": _api_base(),
        "protected_access_token": _protect_token(token),
        "credential_kind": "customer_api_key",
    }
    _atomic_json(_config_path(), config)
    return {"credential_kind": config["credential_kind"]}


def _load_credential() -> tuple[str, dict]:
    path = _config_path()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
        raise CLIError("No usable YunXiaoHe credential; run `python scripts/yxh.py login`") from error
    if not isinstance(config, dict):
        raise CLIError("Credential file is invalid; run login again")
    legacy = {"schema", "api_base", "protected_access_token", "expires_at", "token_id", "version"}
    current = {"schema", "api_base", "protected_access_token", "credential_kind"}
    if set(config) == legacy and config.get("schema") == "yh.skill-credential.v1":
        if not isinstance(config["expires_at"], int) or config["expires_at"] <= int(time.time()):
            raise CLIError("YunXiaoHe Skill token has expired; run login again")
    elif not (set(config) == current and config.get("schema") == "yh.skill-credential.v2"
              and config.get("credential_kind") == "customer_api_key"):
        raise CLIError("Credential file is invalid; run login again")
    _validate_base(config["api_base"])
    if config["api_base"] != _api_base():
        raise CLIError("Credential endpoint differs from the current API endpoint; run login again")
    return _unprotect_token(config["protected_access_token"]), config


def _safe_relative(path: str) -> str:
    if (not path or path.startswith("/") or "?" in path or "#" in path or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        raise CLIError("Invalid API path")
    return path


def _error_message(raw: bytes) -> str:
    try:
        value = json.loads(raw.decode("utf-8"))
        if isinstance(value, dict) and isinstance(value.get("error"), str):
            return value["error"]
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return "request rejected"


def _request(method: str, path: str, payload=None, *, authenticate=True, access_token=None,
             timeout=600, expect_json=True) -> tuple[bytes, dict]:
    relative = _safe_relative(path)
    headers = {"Accept": "application/json", "User-Agent": "yunxiaohe-codex-skill/1.0"}
    if access_token is not None:
        if not TOKEN_RE.fullmatch(access_token):
            raise CLIError("API key format is invalid")
        headers["Authorization"] = "Bearer " + access_token
    elif authenticate:
        token, _config = _load_credential()
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(_api_base() + relative, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise CLIError("YunXiaoHe response exceeded the safe size limit")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        raw = error.read(64 * 1024)
        if error.code == 401:
            raise APIError(error.code, "API key invalid or disabled; choose an active key and run login again") from None
        raise APIError(error.code, _error_message(raw)) from None
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as error:
        raise CLIError(f"Could not reach the YunXiaoHe Skill API: {error}") from None
    if expect_json:
        mime = response_headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if mime not in {"application/json", "application/problem+json"}:
            raise CLIError("YunXiaoHe returned an unexpected response type")
    return raw, response_headers


def _json_request(method: str, path: str, payload=None, *, authenticate=True, access_token=None, timeout=600):
    raw, _headers = _request(method, path, payload, authenticate=authenticate,
                             access_token=access_token, timeout=timeout)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CLIError("YunXiaoHe returned invalid JSON") from error


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


def _require_id(value: str, pattern: re.Pattern, label: str) -> str:
    if not pattern.fullmatch(value):
        raise CLIError(f"Invalid {label} ID")
    return value


def command_login(_args) -> None:
    token = getpass.getpass("YH API key (input hidden): ").strip()
    if not TOKEN_RE.fullmatch(token):
        raise CLIError("API key format is invalid")
    capabilities = _json_request("GET", "capabilities", authenticate=False,
                                 access_token=token, timeout=30)
    if not isinstance(capabilities, dict) or "interaction" not in capabilities:
        raise CLIError("API key validation returned an invalid capability document")
    safe = _save_api_key(token)
    token = ""  # Minimize the lifetime of the Python reference.
    _print({"authenticated": True, **safe, "credential_path": str(_config_path())})


def command_logout(_args) -> None:
    path = _config_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    _print({"authenticated": False, "local_credential_removed": True})


def command_get(args) -> None:
    _print(_json_request("GET", args.command))


def command_create_pi(args) -> None:
    payload = {
        "name": args.name,
        "objective": args.objective,
        "memory_scope": args.memory_scope,
        "memory_peer_pi_id": args.memory_peer,
        "budget_tokens": args.budget,
        "workflow_template_id": args.template,
        "workflow_preferences": {},
        "approval_mode": args.approval,
        "agent_quota": args.agent_quota,
    }
    _print(_json_request("POST", "pis", payload))


def command_talk(args) -> None:
    pi = _require_id(args.pi, PI_RE, "PI")
    _print(_json_request("POST", f"pis/{pi}/dialogue", {
        "content": args.content, "mode": args.mode, "attachment_ids": [],
    }))


def command_dispatch(args) -> None:
    pi = _require_id(args.pi, PI_RE, "PI")
    payload = {
        "pi_id": pi,
        "title": args.title,
        "prompt": args.prompt,
        "role_id": args.role,
        "worker_count": args.workers,
        "tier": args.tier,
        "model_profile": args.model_profile,
        "budget_tokens": args.budget,
        "workflow_id": args.workflow,
        "stage_id": args.stage,
        "loop_template_id": args.loop,
        "loop_round_target": args.rounds,
        "acceptance": args.acceptance,
        "data_boundary": args.data_boundary,
        "return_path": args.return_path,
        "attachment_ids": [],
    }
    _print(_json_request("POST", "tasks", payload))


def _task_snapshot(state: dict, task_id: str) -> dict:
    tasks = [item for item in state.get("tasks", []) if item.get("id") == task_id]
    if len(tasks) != 1:
        raise CLIError("Task is not present in this tenant's current state")
    task = tasks[0]
    pi_id = task.get("pi_id")
    workers = [item for item in state.get("workers", []) if item.get("task_id") == task_id]
    loops = [item for item in state.get("agentic_loops", [])
             if item.get("task_id") == task_id or (pi_id and item.get("pi_id") == pi_id)]
    return {"task": task, "workers": workers, "loops": loops}


def command_wait(args) -> None:
    task_id = _require_id(args.task, TASK_RE, "task")
    deadline = time.monotonic() + args.timeout
    previous = None
    while True:
        state = _json_request("GET", "state", timeout=min(60, max(10, args.interval + 5)))
        snapshot = _task_snapshot(state, task_id)
        status = str(snapshot["task"].get("status", "unknown")).lower()
        worker_states = sorted(str(item.get("status", "unknown")) for item in snapshot["workers"])
        marker = (status, tuple(worker_states))
        if marker != previous:
            print(json.dumps({"progress": True, "task_id": task_id, "status": status,
                              "worker_states": worker_states}, ensure_ascii=False), file=sys.stderr, flush=True)
            previous = marker
        if status in TERMINAL_OK:
            _print(snapshot)
            return
        if status in TERMINAL_BAD:
            _print(snapshot)
            raise CLIError(f"Task ended in terminal state: {status}")
        if time.monotonic() >= deadline:
            _print(snapshot)
            raise CLIError("Wait timeout reached; the task remains available and was not cancelled")
        time.sleep(args.interval)


def command_proposal(args) -> None:
    message = _require_id(args.message, MESSAGE_RE, "message")
    _print(_json_request("POST", f"dialogue/{message}/proposal", {"action": args.action}))


def command_worker(args) -> None:
    worker = _require_id(args.worker, WORKER_RE, "worker")
    _print(_json_request("POST", f"workers/{worker}/actions", {"action": args.action}))


def command_loop(args) -> None:
    loop = _require_id(args.loop_id, LOOP_RE, "loop")
    _print(_json_request("POST", f"loops/{loop}/actions", {"action": args.action}))


def command_export(args) -> None:
    pi = _require_id(args.pi, PI_RE, "PI")
    target = Path(args.output).expanduser().resolve()
    if target.exists() and not args.force:
        raise CLIError(f"Output already exists: {target}; pass --force to replace it")
    raw, headers = _request("POST", f"pis/{pi}/exports/{args.format}", {}, expect_json=False)
    mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if args.format == "pdf":
        if mime != "application/pdf" or not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-2048:]:
            raise CLIError("Refusing to save an invalid PDF response")
    elif mime not in {"text/markdown", "text/plain", "application/octet-stream"}:
        raise CLIError("Refusing to save an unexpected Markdown response")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    _print({"saved": str(target), "bytes": len(raw), "format": args.format})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use YunXiaoHe as a structured Codex Skill")
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="store and validate a customer-managed API key")
    login.set_defaults(func=command_login)

    logout = commands.add_parser("logout", help="remove the API key copy stored on this device")
    logout.set_defaults(func=command_logout)

    for name, help_text in (("capabilities", "show the stable Skill contract"),
                            ("state", "read tenant-scoped workspace state"),
                            ("registries", "read available roles, skills, services, and workflows")):
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(func=command_get)

    create = commands.add_parser("create-pi", help="create a tenant-scoped principal investigator")
    create.add_argument("--name", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--memory-scope", default="isolated",
                        choices=("isolated", "read_project", "read_and_propose", "selected_pi_bidirectional",
                                 "full_project_share", "ephemeral_only"))
    create.add_argument("--memory-peer")
    create.add_argument("--budget", type=int, default=250000)
    create.add_argument("--template", default="adaptive")
    create.add_argument("--approval", default="require_approval", choices=("require_approval", "full_access"))
    create.add_argument("--agent-quota", type=int, default=8)
    create.set_defaults(func=command_create_pi)

    talk = commands.add_parser("talk", help="send a PI-level discussion or research message")
    talk.add_argument("--pi", required=True)
    talk.add_argument("--content", required=True)
    talk.add_argument("--mode", default="plain", choices=("plain", "research"))
    talk.set_defaults(func=command_talk)

    dispatch = commands.add_parser("dispatch", help="dispatch a structured tracked task")
    dispatch.add_argument("--pi", required=True)
    dispatch.add_argument("--title", required=True)
    dispatch.add_argument("--prompt", required=True)
    dispatch.add_argument("--role", default="investigator")
    dispatch.add_argument("--workers", type=int, default=1)
    dispatch.add_argument("--budget", type=int, default=12000)
    dispatch.add_argument("--tier", default="auto", choices=("auto", "T0", "T1", "T2", "T3"))
    dispatch.add_argument("--model-profile", default="auto")
    dispatch.add_argument("--workflow", default="auto")
    dispatch.add_argument("--stage")
    dispatch.add_argument("--loop", default="inherit",
                          choices=("inherit", "auto", "linear", "review-revision", "verified-improvement"))
    dispatch.add_argument("--rounds", type=int)
    dispatch.add_argument("--acceptance", required=True)
    dispatch.add_argument("--data-boundary", required=True)
    dispatch.add_argument("--return-path", default="Return an incremental receipt to the PI conversation")
    dispatch.set_defaults(func=command_dispatch)

    wait = commands.add_parser("wait", help="monitor a task until terminal state without cancelling it")
    wait.add_argument("task")
    wait.add_argument("--timeout", type=int, default=3600)
    wait.add_argument("--interval", type=int, default=10)
    wait.set_defaults(func=command_wait)

    proposal = commands.add_parser("proposal", help="dispatch or dismiss an explicit PI proposal")
    proposal.add_argument("message")
    proposal.add_argument("action", choices=("dispatch", "dismiss"))
    proposal.set_defaults(func=command_proposal)

    worker = commands.add_parser("worker", help="send a scoped worker control action")
    worker.add_argument("worker")
    worker.add_argument("action")
    worker.set_defaults(func=command_worker)

    loop = commands.add_parser("loop", help="continue, hold, cancel, or complete an agentic loop")
    loop.add_argument("loop_id")
    loop.add_argument("action", choices=("continue", "hold", "cancel", "complete"))
    loop.set_defaults(func=command_loop)

    export = commands.add_parser("export", help="export a PI conversation as Markdown or PDF")
    export.add_argument("--pi", required=True)
    export.add_argument("--format", required=True, choices=("markdown", "pdf"))
    export.add_argument("--output", required=True)
    export.add_argument("--force", action="store_true")
    export.set_defaults(func=command_export)
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if getattr(args, "timeout", 1) <= 0 or getattr(args, "interval", 1) <= 0:
            raise CLIError("Timeout and interval must be positive")
        if getattr(args, "budget", 1000) < 256:
            raise CLIError("Token budget must be at least 256")
        if not 1 <= getattr(args, "workers", 1) <= 16:
            raise CLIError("Worker count must be between 1 and 16")
        if not 1 <= getattr(args, "agent_quota", 1) <= 32:
            raise CLIError("Agent quota must be between 1 and 32")
        args.func(args)
        return 0
    except (CLIError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted; no remote cancellation was sent", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
