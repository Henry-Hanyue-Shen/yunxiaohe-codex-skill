# YunXiaoHe Local Workspace Preview

Local Workspace is the device-local data plane for the `yunxiaohe-client` Codex Skill. It deliberately reuses Codex as the interface and execution environment instead of shipping a separate YXH GUI, updater, background daemon, or localhost web service.

## Boundary

`python scripts/yxh.py local ...` delegates to the dependency-free `scripts/local_workspace.py` data plane. Local commands make no network requests. The data plane stores its manifest and staged outputs under the bound root's `.yxh/` directory.

The local manifest contains:

- a random workspace ID;
- a display name;
- relative file paths;
- opaque object IDs;
- file size, MIME type, modification time, and SHA-256;
- `metadata` or `full-text` local access;
- relative records for staged outputs.

It does not contain the absolute workspace path, YH credentials, provider credentials, or file contents. The `context` command emits only portable metadata. The server's 3 GB workspace quota is not used.

The current public YXH API does not provide a verified local-worker callback or content-addressed pull protocol. Therefore:

1. remote workers cannot dereference `local://...` references;
2. Codex must perform file-dependent operations locally;
3. a summary, extract, or result is sent to a remote PI only after a separate, explicit disclosure decision;
4. local mode never silently falls back to cloud upload.

Do not claim that a remote task processed a local file unless the service later returns a verified receipt for a supported local-worker protocol.

## Initialize

Bind an existing directory:

```bash
python scripts/yxh.py local init PATH --name "Project workspace"
```

Initialization creates `.yxh/workspace.json` and `.yxh/outputs/`. It does not scan, register, upload, move, or delete project files.

Commands other than `init` accept `--workspace PATH`. The path may be the root or a descendant; if omitted, discovery starts at the current directory and walks upward.

## Register Files

Metadata-only is the default:

```bash
python scripts/yxh.py local --workspace PATH add relative/data.csv
```

Allow bounded local text reads:

```bash
python scripts/yxh.py local --workspace PATH add relative/notes.md --access full-text
```

Registration streams the file through SHA-256. Re-registering the same relative path preserves its opaque object ID while approving the current revision. A read fails closed if size or hash has changed since registration.

The CLI rejects:

- paths outside the bound root;
- `..` traversal;
- symlinks, junctions, and other reparse points;
- `.yxh`, `.git`, `.hg`, and `.svn` contents;
- common credential filenames and private-key formats.

It registers regular files only. Directory-wide access is intentionally absent from the preview; select the files actually needed for the task.

## Inspect and Read

```bash
python scripts/yxh.py local --workspace PATH status
python scripts/yxh.py local --workspace PATH list
python scripts/yxh.py local --workspace PATH verify
python scripts/yxh.py local --workspace PATH context [LOCAL_REF ...]
python scripts/yxh.py local --workspace PATH read LOCAL_REF --offset 0 --max-bytes 262144
```

`list` performs a lightweight presence/size check. `verify` rehashes every registered file. `read` requires `full-text`, verifies the approved hash before reading, and supports bounded chunks up to 8 MiB. It accepts UTF-8 and BOM-marked UTF-16/32 text, plus common GB18030 and Windows-1252 CSV exports. The response reports the detected `encoding` and the next byte offset. For an ambiguous export, supply `--encoding gb18030` or `--encoding cp1252`, and reuse that choice when reading subsequent chunks. Only explicitly registered, allowlisted text files are read; binary formats require separate local tools or metadata mode. Encoding detection is not a guarantee of the document's semantic integrity.

`context` contains no file contents or absolute paths. It is safe to use as a manifest, but its filenames and hashes can still be sensitive project metadata and should be shared only within the user's requested scope.

## Stage Deliverables

Stage a file that already exists inside the workspace:

```bash
python scripts/yxh.py local --workspace PATH stage-output \
  --task TASK_LABEL \
  --source relative/result.md
```

The CLI copies it atomically to `.yxh/outputs/TASK_LABEL/`, calculates SHA-256, and records the relative output path. Existing staged files are never replaced unless `--force` is supplied. This is local bookkeeping, not a cloud export.

List outputs:

```bash
python scripts/yxh.py local --workspace PATH list-outputs
python scripts/yxh.py local --workspace PATH list-outputs --task TASK_LABEL
```

## Remove Access

```bash
python scripts/yxh.py local --workspace PATH remove LOCAL_REF
```

This removes only the manifest reference. It never deletes the user's source file. There is no recursive delete or workspace-destroy command.

## Planned Integration Gate

The intended hybrid mode keeps YH customer authorization and the hosted DS/model service available, while a user-authorized Codex conversation (and, where the host supports it, Codex subagents) can accept PI-assigned local-worker jobs. The harness should route by task capability and data boundary, not by a hard-coded model. This is a target design, **not a capability in the current release**: no remote YXH task can currently spawn or control a Codex conversation through this Skill.

Local Workspace should leave preview only after the public service defines and tests all of the following:

- device pairing bound to a customer API key;
- short-lived task-scoped capability tokens;
- an outbound-only local worker channel;
- content-addressed request and result receipts;
- explicit per-task file grants and revocation;
- resumable failure semantics with no silent cloud upload;
- end-to-end tests proving tenant isolation, path confinement, and correct offline behavior.

The local worker must explicitly disclose which selected excerpts or derived data, if any, it sends to the hosted DS service. Keeping source files on the device does not mean a remote model can process their contents without data transmission. Losing the online YH authorization lease must stop new work; any in-flight job needs a bounded, receipt-backed failure or resume path rather than silently falling back to cloud storage.

Until then, this Skill provides a real local storage and access layer for Codex, not a claimed remote-local execution bridge.
