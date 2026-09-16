# YunXiaoHe Codex Skill

This repository contains the public `yunxiaohe-client` Skill for registered YH Intelligence customers. It lets Codex use YunXiaoHe as a structured PI/worker/loop harness—not merely as a chat endpoint.

The repository contains no customer credentials. A registered user signs in at [yh-intel.cn/client/](https://yh-intel.cn/client/), creates one of up to three customer-managed API keys, and enters it only in the CLI's hidden local prompt. Keys can be viewed again or disabled individually from the customer center.

Ask Codex to install the `yunxiaohe-client` skill from this repository, or copy the [`yunxiaohe-client`](yunxiaohe-client/) directory into your Codex skills directory. Then invoke `$yunxiaohe-client`. The bundled CLI requires Python 3.10+ and only uses the standard library.

Official service: [yh-intel.cn](https://yh-intel.cn/)

Contact: [bot@yh-intel.com](mailto:bot@yh-intel.com) — expected response within one week.

## Security

- Never paste a customer password or API key into chat.
- Create, review, and disable API keys only while signed in to the official customer center.
- The local CLI protects keys with Windows DPAPI or a POSIX mode-0600 file.
- Password changes, account reset/disable, product revocation, or manual key disable revoke access.
- The API derives tenant identity from the token and never accepts a client-supplied tenant ID.

See [`references/api.md`](yunxiaohe-client/references/api.md) for the public v1 contract.
