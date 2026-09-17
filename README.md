# YunXiaoHe Codex Skill

This repository contains the public `yunxiaohe-client` Skill for registered YH Intelligence customers. It lets Codex use YunXiaoHe as a structured PI/worker/loop harness—not merely as a chat endpoint. The same Skill also includes a preview local-workspace data plane, so Codex can work with files on the user's device without maintaining a separate YXH desktop GUI or consuming the server's 3 GB file quota.

The repository contains no customer credentials. A registered user signs in at [yh-intel.cn/client/](https://yh-intel.cn/client/), creates one of up to three customer-managed API keys, and enters it only in the CLI's hidden local prompt. Keys can be viewed again or disabled individually from the customer center.

## Start in five minutes

1. Sign in to the [YH customer center](https://yh-intel.cn/client/) and open **Codex API keys**. Create a key; do not paste it into chat.
2. Ask Codex: `Install the yunxiaohe-client skill from https://github.com/Henry-Hanyue-Shen/yunxiaohe-codex-skill/tree/main/yunxiaohe-client`
3. In your own terminal, open the installed Skill directory and run `python scripts/yxh.py login`. The prompt hides your key while you type.
4. On your next Codex turn, invoke `$yunxiaohe-client` and describe the work you want YunXiaoHe to carry out.

The bundled CLI requires Python 3.10+ and uses only the standard library. For exact Windows, macOS, and Linux commands—and a complete PI → task → result walkthrough—read the [Getting Started tutorial](docs/getting-started.md).

Official service: [yh-intel.cn](https://yh-intel.cn/)

Contact: [bot@yh-intel.com](mailto:bot@yh-intel.com) — expected response within one week.

## Local Workspace Preview

Local Workspace is an installation mode of this Skill, not a second application. Codex remains the interface and runtime. The bundled standard-library CLI binds one explicit directory, registers files by opaque `local://...` references, enforces metadata-only or full-text access, detects changed files, and stages outputs atomically under `.yxh/outputs/`.

```bash
python scripts/yxh.py local init ./my-project --name "My project"
python scripts/yxh.py local --workspace ./my-project add data/input.csv --access metadata
python scripts/yxh.py local --workspace ./my-project status
```

No local-mode command uses the network. Its portable context contains relative paths, sizes, MIME types, and SHA-256 hashes—never absolute paths or file contents. A remote YXH worker cannot open a local reference today; Codex must perform file-dependent work locally, or the user must separately choose what derived text to disclose to the remote workflow. This boundary is intentional and the mode remains a preview until the public API exposes a verified local-worker handshake.

## Security

- Never paste a customer password or API key into chat.
- Create, review, and disable API keys only while signed in to the official customer center.
- The local CLI protects keys with Windows DPAPI or a POSIX mode-0600 file.
- Password changes, account reset/disable, product revocation, or manual key disable revoke access.
- The API derives tenant identity from the token and never accepts a client-supplied tenant ID.
- Local Workspace rejects traversal, symlinks/junctions/reparse points, VCS control data, credential files, and private-key formats. Removing a reference never deletes the source file.

See the [Getting Started tutorial](docs/getting-started.md) for normal use, [`references/api.md`](yunxiaohe-client/references/api.md) for the public v1 contract, and [`references/local-workspace.md`](yunxiaohe-client/references/local-workspace.md) for the local data-plane contract.
