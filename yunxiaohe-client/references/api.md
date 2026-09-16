# YunXiaoHe Skill API v1

Official base URL:

`https://yh-intel.cn/client/yunxiaohe/skill/v1/`

All responses are private and `no-store`. The service does not enable CORS. Except for `login`, every request requires `Authorization: Bearer yhsk_...`. Browser cookies are not accepted on this surface.

## Authentication

### `POST login`

```json
{"username":"registered-user","password":"entered-locally"}
```

Returns a tenant-scoped, seven-day, revocable token. A customer may have at most five active Skill tokens; issuing another revokes the oldest. The CLI never prints the raw token. Login fails when the account is disabled, still requires its initial password change, or lacks a YunXiaoHe entitlement.

### `POST logout`

Body: `{}`. Revokes exactly the presented token.

## Discovery and State

- `GET capabilities` — stable public API capabilities.
- `GET state` — the caller's YunXiaoHe bootstrap state, including PIs, tasks, workers, loops, messages, workflows, resources, and usage.
- `GET registries` — roles, skills, services, workflows, and model-route registries available to this runtime.

Use service-returned IDs. The public surface accepts no query strings.

## Create a PI

### `POST pis`

Typical body:

```json
{
  "name": "Project PI",
  "objective": "Concrete objective",
  "memory_scope": "isolated",
  "memory_peer_pi_id": null,
  "budget_tokens": 250000,
  "workflow_template_id": "adaptive",
  "workflow_preferences": {},
  "approval_mode": "require_approval",
  "agent_quota": 8
}
```

Use `require_approval` unless the user explicitly authorizes the runtime's bounded full-access mode. Memory sharing must be an explicit choice.

## PI Dialogue

### `POST pis/{pi_id}/dialogue`

```json
{"content":"Discuss or plan this request","mode":"plain","attachment_ids":[]}
```

Modes are `plain` and `research`. This endpoint starts PI reasoning but does not replace structured task dispatch.

### `POST dialogue/{message_id}/proposal`

```json
{"action":"dispatch"}
```

`action` is `dispatch` or `dismiss`.

## Dispatch a Structured Task

### `POST tasks`

The runtime validates the exact schema. A broadly compatible payload is:

```json
{
  "pi_id": "pi-0123456789ab",
  "title": "Bounded research task",
  "prompt": "Exact instructions",
  "role_id": "investigator",
  "worker_count": 1,
  "tier": "auto",
  "model_profile": "auto",
  "budget_tokens": 12000,
  "workflow_id": "auto",
  "stage_id": null,
  "loop_template_id": "inherit",
  "loop_round_target": null,
  "acceptance": "Completion criteria",
  "data_boundary": "Authorized data and environments only",
  "return_path": "Incremental receipt to the PI conversation",
  "attachment_ids": []
}
```

Roles and workflow IDs come from `registries` and `state`. Supported loop choices currently include `inherit`, `auto`, `linear`, `review-revision`, and `verified-improvement`. `budget_tokens` is planning and cost telemetry, not permission to silently broaden scope.

## Runtime Control

### `POST workers/{worker_id}/actions`

```json
{"action":"reclaim"}
```

Use only actions exposed by current state/UI semantics. Interrupting actions require user authorization.

### `POST loops/{loop_id}/actions`

```json
{"action":"continue"}
```

Known actions include `continue`, `hold`, `cancel`, and `complete`, subject to current state transitions.

## Export

- `POST pis/{pi_id}/exports/markdown` with body `{}`.
- `POST pis/{pi_id}/exports/pdf` with body `{}`.

The CLI validates PDF signatures before saving and uses atomic file replacement. Exported content is private customer material; do not commit it to the public Skill repository.

## Errors

- `400` malformed or ambiguous request.
- `401` invalid, expired, or revoked Skill token; re-run local login.
- `403` browser ambient credentials, missing product authority, or disallowed request context.
- `404` endpoint/ID not available to this tenant.
- `413` body too large.
- `415` JSON content type required.
- `429` bounded login or tenant concurrency rate limit.
- `503` verified origin/runtime is temporarily unavailable.

Never retry mutations blindly. State reads may be retried; after an uncertain mutation, call `state` and reconcile by returned IDs before deciding whether to submit again.
