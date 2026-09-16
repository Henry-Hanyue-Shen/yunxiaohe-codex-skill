# YunXiaoHe Codex Skill

This repository contains the public `yunxiaohe-client` Skill for registered YH Intelligence customers. It lets Codex use YunXiaoHe as a structured PI/worker/loop harness—not merely as a chat endpoint.

The repository contains no customer credentials. A user authenticates interactively with an existing YH customer account; the service exchanges that password for a tenant-scoped, expiring, revocable Skill token.

Ask Codex to install the `yunxiaohe-client` skill from this repository, or copy the [`yunxiaohe-client`](yunxiaohe-client/) directory into your Codex skills directory. Then invoke `$yunxiaohe-client`. The bundled CLI requires Python 3.10+ and only uses the standard library.

Official service: [yh-intel.cn](https://yh-intel.cn/)  
Contact: [bot@yh-intel.com](mailto:bot@yh-intel.com) — expected response within one week.

## Security

- Never paste a customer password or Skill token into chat.
- Passwords are used only for the local interactive exchange and are not stored.
- Tokens are encrypted with Windows DPAPI or stored in a POSIX mode-0600 file.
- Password changes, account reset/disable, product revocation, explicit logout, and expiry revoke access.
- The API derives tenant identity from the token and never accepts a client-supplied tenant ID.

See [`references/api.md`](yunxiaohe-client/references/api.md) for the public v1 contract.
