# reasoning-efforts

Adds `--reasoning-efforts`: the operator-declared effort vocabulary this
deployment actually distinguishes, enforced at the serving boundary.

**Commits:** `e5b5939ecc` (main) / `e...` v0.5.18 backport · **Files:**
`server_args.py`, `entrypoints/openai/serving_chat.py`,
`test/registered/unit/entrypoints/openai/test_serving_chat.py`

## The problem

Clients express reasoning depth as an effort level, but what interprets it is
the chat template inside the model artifact — and templates commonly **fold**
unknown levels instead of erroring:

- Qwen3.8-Flash-Next: absent → `xhigh` (via `|default`); `medium` accepted but
  injects **no instruction at all** (token-identical to no effort concept).
- GLM-5.3: `reasoning_effort if reasoning_effort in ['low','high'] else 'max'`
  — a client asking `minimal` silently gets the **most expensive** mode.

At the call site a silently remapped level is indistinguishable from an
honored one. Same for "disable thinking" on always-thinking models: the
Anthropic surface already raises (`apply_reasoning_enabled`), but the OpenAI
surface (`reasoning_effort:"none"`, `enable_thinking:false`) is silently
ignored.

## Principle

Honor verbatim or reject naming the levels this deployment distinguishes.
Never remap, never default-upgrade, never let the template's fallback decide.

## Semantics (fleet contract — profile key `reasoning_efforts`)

| Rule | Meaning |
|---|---|
| Flag unset / empty | Mechanism **off** — stock passthrough. Opt-in per deployment. |
| Values | Opaque, case-sensitive strings, exact match. No aliases, no ranking. |
| Unlisted level | `ValueError` → **400** naming the declared list (both OpenAI and Anthropic surfaces — the Anthropic one via `_conversion_client_error` from the `anthropic-effort-400` set). |
| `none` | Ordinary member = "model can genuinely disable reasoning". Absent → disable requests (effort `none`, or explicit `enable_thinking`/`thinking` false kwarg) are **rejected**, not silently ignored. |
| Floats | Matched by `str()` form — a deployment distinguishing `0.5` lists `"0.5"`. Note `0.50` parses to the float `0.5` → `"0.5"`. |
| Unset effort in a request | Passes through — the model's own default is not a client claim. |
| List order | Cosmetic; only affects the error message. |

## Where it checks

`OpenAIServingChat._validate_reasoning_effort_vocabulary`, called from
`_process_messages` — the true convergence point. Coverage, verified per
call site:

| Surface | Reaches the check via |
|---|---|
| `/v1/chat/completions` | `_convert_to_internal_request` → `_process_messages` |
| Anthropic `/v1/messages` | the adapter calls the same convert path (400 via `_conversion_client_error`) |
| `/v1/responses` (non-harmony) | calls `_process_messages` **directly** — a convert-level check missed it |
| `/v1/tokenize` | same direct call |
| harmony (gpt-oss) Responses | **not covered** — renders no chat template |

Both spellings are validated (top-level field and
`chat_template_kwargs["reasoning_effort"]`), because only the convert path
pops the ctk copy — on the direct callers the ctk value is what the template
reads. The check sits after the `default_chat_template_kwargs` merge, so an
operator default outside the declared vocabulary fails loudly on the first
request. Engine-internal rewrites that happen
*before* convert (hunyuan → `no_think`, inkling → `none`, mistral → `medium`)
arrive at the check in rewritten form — an operator setting a vocabulary on
those models lists the rewritten spellings. The dsv4/kimi_k3/inkling encoders
bypass `apply_chat_template` but **not** this check.

Not covered: operator-side `--default-chat-template-kwargs` (merged after
convert; operator intent, not a client claim).

## Applicability

- **Applies to stock `upstream/main`:** yes (`feat/reasoning-efforts`).
- **One backport serves both deployed runtimes:** `overlay/reasoning-efforts-v0.5.18`
  applies cleanly to `v0.5.18` **and** PR #36497 @ `7c66045d7` — the check uses
  the `self.tokenizer_manager.server_args` idiom both bases share.
- **Shares `server_args.py` with `log-requests-events`** — not disjoint, but
  composition is **verified**: both orders apply cleanly on `upstream/main`,
  `v0.5.18`, and `7c66045d7`.
- **Off by default.** Unset flag = byte-for-byte stock behaviour.

## Verification

- Validator logic: 13/13 scenario checks (passthrough, exact match, rejection
  message content/order, floats, both `none` semantics directions).
- 7 unit tests added to `test_serving_chat.py`.
- **Pending:** full unittest run + NS-coverage guardrails on the container's
  venv — the container was down when this landed. Run before deploying:
  `test.registered.unit.entrypoints.openai.test_serving_chat`,
  `test.registered.unit.test_server_args_namespaces`,
  `test.registered.unit.test_runtime_context_config_bags`.

## Remove when

Accepted upstream. This is a general serving-honesty mechanism, not a local
quirk — same class as `log-requests-events`.

## Extract

```bash
# deployment (either runtime)
git diff v0.5.18..overlay/reasoning-efforts-v0.5.18 -- python/ > reasoning-efforts.patch
# upstreaming
BASE=$(git merge-base upstream/main feat/reasoning-efforts)
git diff $BASE..feat/reasoning-efforts -- python/ > reasoning-efforts.patch
```
