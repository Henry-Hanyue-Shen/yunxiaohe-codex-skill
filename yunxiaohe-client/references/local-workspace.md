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

Allow bounded local UTF-8 reads:

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

`list` performs a lightweight presence/size check. `verify` rehashes every registered file. `read` requires `full-text`, verifies the approved hash before reading, supports bounded chunks up to 8 MiB, and currently accepts UTF-8 text only.

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

Local Workspace should leave preview only after the public service defines and tests all of the following:

- device pairing bound to a customer API key;
- short-lived task-scoped capability tokens;
- an outbound-only local worker channel;
- content-addressed request and result receipts;
- explicit per-task file grants and revocation;
- resumable failure semantics with no silent cloud upload;
- end-to-end tests proving tenant isolation, path confinement, and correct offline behavior.

Until then, this Skill provides a real local storage and access layer for Codex, not a claimed remote-local execution bridge.
