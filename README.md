# YunXiaoHe Codex Skill

This repository contains the public `yunxiaohe-client` Skill for registered YH Intelligence customers. It lets Codex use YunXiaoHe as a structured PI/worker/loop harness—not merely as a chat endpoint.

The repository contains no customer credentials. A registered user signs in at [yh-intel.cn/client/](https://yh-intel.cn/client/), creates one of up to three customer-managed API keys, and enters it only in the CLI's hidden local prompt. Keys can be viewed again or disabled individually from the customer center.

## Start in five minutes

1. Sign in to the [YH customer center](https://yh-intel.cn/client/) and open **Codex API keys**. Create a key; do not paste it into chat.
2. Ask Codex: `Install the yunxiaohe-client skill from https://github.com/Henry-Hanyue-Shen/yunxiaohe-codex-skill/tree/main/yunxiaohe-client`
3. In your own terminal, open the installed Skill directory and run `python scripts/yxh.py login`. The prompt hides your key while you type.
4. On your next Codex turn, invoke `$yunxiaohe-client` and describe the work you want YunXiaoHe to carry out.

The bundled CLI requires Python 3.10+ and uses only the standard library. For exact Windows, macOS, and Linux commands—and a complete PI → task → result walkthrough—read the [Getting Started tutorial](docs/getting-started.md).

Official service: [yh-intel.cn](https://yh-intel.cn/)

Contact: [bot@yh-intel.com](mailto:bot@yh-intel.com) — expected response within one week.

## Security

- Never paste a customer password or API key into chat.
- Create, review, and disable API keys only while signed in to the official customer center.
- The local CLI protects keys with Windows DPAPI or a POSIX mode-0600 file.
- Password changes, account reset/disable, product revocation, or manual key disable revoke access.
- The API derives tenant identity from the token and never accepts a client-supplied tenant ID.

See the [Getting Started tutorial](docs/getting-started.md) for normal use and [`references/api.md`](yunxiaohe-client/references/api.md) for the public v1 contract.
