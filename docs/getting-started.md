# YunXiaoHe Client: Getting Started

This tutorial connects Codex to your authorized YunXiaoHe workspace. It uses YunXiaoHe's structured PI, task, worker, and loop workflow—not a generic chat proxy.

## Before you begin

You need:

- a registered YH Intelligence customer account;
- YunXiaoHe enabled for that account;
- the initial password already changed, if your account was issued with one;
- Codex and Python 3.10 or newer.

Your workspace and product access remain tied to your YH account. Installing the public Skill does not create an account or grant access by itself.

## 1. Install the Skill

The simplest route is to send this exact prompt to Codex:

```text
Install the yunxiaohe-client skill from https://github.com/Henry-Hanyue-Shen/yunxiaohe-codex-skill/tree/main/yunxiaohe-client
```

Codex installs the `yunxiaohe-client` directory into your local skills folder. Use the Skill on your next turn.

If you prefer a manual installation, clone this repository and copy the `yunxiaohe-client` directory to:

- Windows: `%USERPROFILE%\.codex\skills\yunxiaohe-client`
- macOS or Linux: `~/.codex/skills/yunxiaohe-client`

If you have set `CODEX_HOME`, use its `skills` directory instead. Do not copy the whole repository into the Skill directory; `SKILL.md` must sit directly inside `yunxiaohe-client`.

## 2. Create a customer API key

1. Sign in at [yh-intel.cn/client/](https://yh-intel.cn/client/).
2. Open **Codex API keys**.
3. Create a key, or select one of your existing active keys.

Each account may keep up to three active keys. You can reveal an active key again or disable it from the customer center. Treat it like a password: never paste it into a Codex conversation, issue, screenshot, or repository.

## 3. Authenticate on this device

Open a terminal in the installed Skill directory.

PowerShell on Windows:

```powershell
Set-Location "$env:USERPROFILE\.codex\skills\yunxiaohe-client"
py -3 scripts/yxh.py login
```

macOS or Linux:

```bash
cd "${CODEX_HOME:-$HOME/.codex}/skills/yunxiaohe-client"
python3 scripts/yxh.py login
```

Paste the API key only into the terminal prompt. Input is hidden. The CLI validates the key without printing it and stores a protected local copy: Windows DPAPI on Windows, or a mode-0600 file on POSIX systems.

Confirm the connection:

```bash
python scripts/yxh.py capabilities
python scripts/yxh.py state
python scripts/yxh.py registries
```

On Windows, replace `python` with `py -3` if that is how Python is installed.

## 4. Use YunXiaoHe from Codex

For most users, Codex should operate the CLI through the Skill. A useful first request is:

```text
$yunxiaohe-client Use my authorized YunXiaoHe workspace. Check the available workflows first, then create or reuse an isolated PI and research [your topic]. Return progress while the task runs and export the final result as Markdown.
```

Codex should inspect the service's current state and registries before choosing IDs. It should reuse a suitable PI when possible, report queued/running/held/failed states honestly, and wait for the whole task—not only the first worker—to reach a terminal result.

Use a plain PI conversation for clarification or planning. Ask for a tracked task when you need workers, budgets, acceptance criteria, data boundaries, progress, and an exportable deliverable.

### Optional: keep project files on this device

If the files should remain local, initialize a Local Workspace instead of uploading them to the 3 GB cloud workspace. This is part of the installed Skill; there is no separate GUI or background service.

PowerShell:

```powershell
py -3 scripts/yxh.py local init "C:\path\to\project" --name "Project name"
py -3 scripts/yxh.py local --workspace "C:\path\to\project" add "data\input.csv" --access metadata
```

macOS or Linux:

```bash
python3 scripts/yxh.py local init /path/to/project --name "Project name"
python3 scripts/yxh.py local --workspace /path/to/project add data/input.csv --access metadata
```

Choose `metadata` when the agent only needs the name, size, type, and content hash. Choose `full-text` only when the user wants Codex to read a UTF-8 text file locally. Neither choice uploads the file. A remote YunXiaoHe worker cannot open a `local://...` reference in the current preview, so keep file-dependent execution in Codex and share only explicitly approved summaries or extracts with the remote PI.

Useful checks:

```bash
python scripts/yxh.py local --workspace /path/to/project status
python scripts/yxh.py local --workspace /path/to/project list
python scripts/yxh.py local --workspace /path/to/project verify
python scripts/yxh.py local --workspace /path/to/project context
```

To record a finished artifact without uploading it:

```bash
python scripts/yxh.py local --workspace /path/to/project stage-output --task TASK_LABEL --source relative/result.md
```

The staged copy is written atomically to `.yxh/outputs/TASK_LABEL/`. Local Workspace has no artificial 3 GB quota; actual free disk space is shown by `status`.

## 5. Direct CLI walkthrough

You normally do not need to run these commands yourself, but they show exactly what the Skill does.

Create an isolated PI:

```bash
python scripts/yxh.py create-pi --name "Market Research PI" --objective "Produce an evidence-backed market map"
```

Copy the returned PI ID, then dispatch a bounded task:

```bash
python scripts/yxh.py dispatch --pi PI_ID --title "Map the target market" --prompt "Identify the main segments, current participants, and evidence gaps." --role investigator --workers 1 --budget 12000 --workflow auto --loop inherit --acceptance "A sourced comparison with uncertainties clearly marked" --data-boundary "Public web sources and my authorized YH workspace only" --return-path "Return incremental progress to the PI conversation"
```

Copy the returned task ID and monitor it without cancelling the remote work:

```bash
python scripts/yxh.py wait TASK_ID --timeout 3600 --interval 10
```

Export the PI conversation when the work is complete:

```bash
python scripts/yxh.py export --pi PI_ID --format markdown --output result.md
python scripts/yxh.py export --pi PI_ID --format pdf --output result.pdf
```

The CLI validates a PDF response before saving it and refuses to overwrite an existing file unless you add `--force`.

## 6. Fast work and deeper work

Do not guess a workflow name. Run `registries` and use what your current account and runtime expose.

- For a short, time-sensitive request, ask Codex to use a service-returned quick template, one worker, and a linear loop.
- For research that benefits from critique or revision, use a normal/adaptive workflow and the loop returned by the service.
- Use `talk` for discussion; use `dispatch` when the result must be tracked and delivered.

## 7. Revoke access

To remove only the credential stored on the current device:

```bash
python scripts/yxh.py logout
```

To revoke the key itself, disable it in **Codex API keys** in the customer center. Password changes, account reset or disable, YunXiaoHe entitlement removal, and manual key disable also revoke API access.

## Troubleshooting

| Result | Meaning | What to do |
| --- | --- | --- |
| `401` | The key is invalid or disabled | Choose an active key and run `login` again locally. |
| `403` | The account lacks YunXiaoHe authority, or the request context is not allowed | Ask your YH administrator to check product access. |
| `404` | The endpoint or ID is not available to your tenant | Run `state` and `registries`; use only returned IDs. |
| `429` | Your tenant reached a bounded concurrency limit | Let current work finish before submitting more. |
| `503` | The verified YunXiaoHe runtime is temporarily unavailable | Keep the returned IDs, wait, and retry a state read. Do not blindly repeat a mutation. |

If a create or dispatch request ends with an uncertain network result, read `state` first. Reconcile the returned PI and task IDs before submitting anything again.

For endpoint schemas, read the [public API reference](../yunxiaohe-client/references/api.md). For account help, contact [bot@yh-intel.com](mailto:bot@yh-intel.com); expected response is within one week.

For local file boundaries and the full command contract, read the [Local Workspace reference](../yunxiaohe-client/references/local-workspace.md).
