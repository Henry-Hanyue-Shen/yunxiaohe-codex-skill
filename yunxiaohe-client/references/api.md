# YunXiaoHe Skill API v1

Official base URL:

`https://yh-intel.cn/client/yunxiaohe/skill/v1/`

All responses are private and `no-store`. The service does not enable CORS. Every request requires `Authorization: Bearer yhsk_...`. Browser cookies are not accepted on this surface.

## Authentication

Sign in at `https://yh-intel.cn/client/` and open **Codex API keys**. Each registered customer may keep at most three active keys. The customer center can display an active key again and can disable each key individually. Keys are tenant-scoped and fail immediately when disabled, when the account password is changed/reset, when the account is disabled, or when YunXiaoHe access is removed.

Run `python scripts/yxh.py login` and enter a key only in the hidden local prompt. The CLI validates it with `GET capabilities`, never prints it, and stores only a protected device-local copy. CLI `logout` removes that local copy; remote disable remains an explicit customer-center action.

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
- `401` invalid or disabled API key; choose an active key and re-run local login.
- `403` browser ambient credentials, missing product authority, or disallowed request context.
- `404` endpoint/ID not available to this tenant.
- `413` body too large.
- `415` JSON content type required.
- `429` bounded tenant concurrency rate limit.
- `503` verified origin/runtime is temporarily unavailable.

Never retry mutations blindly. State reads may be retried; after an uncertain mutation, call `state` and reconcile by returned IDs before deciding whether to submit again.
