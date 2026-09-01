# Deploy: `--reasoning-efforts` (honest effort vocabulary)

**For:** the deployment team · **Written:** 2026-09-01 · implements the fleet's
per-profile `reasoning_efforts` contract (your reference: `roles/llamacpp`).

## What it does

The profile key you already have:

```yaml
sglang_profiles:
  qwen38-flash-next-fp8:
    ...
    reasoning_efforts: [xhigh, medium, low, none]
```

renders for SGLang as:

```
--reasoning-efforts xhigh medium low none
```

(space-separated `nargs`, not comma-joined — that is the one rendering
difference from llamacpp's `--reasoning-effort-levels low,high,max`.)

Semantics are the contract's, unchanged: unset/empty = stock passthrough;
opaque case-sensitive strings, exact match; unlisted level → **400 naming the
declared list** on both the OpenAI and Anthropic surfaces; `none` present =
model can genuinely disable reasoning, absent = disable-thinking requests
(`reasoning_effort:"none"`, `enable_thinking:false`, `thinking:false`) are
rejected instead of silently ignored; list order only affects the error
message.

## Suggested vocabularies for the current profiles

| Profile | Suggested `reasoning_efforts` | Why |
|---|---|---|
| `qwen38-flash-next-*` | `[xhigh, medium, low, none]` | The template's exact accepted set, plus `none` because `enable_thinking:false` genuinely works (the template pre-closes the think block). **Know what you are listing:** `medium` passes validation but injects *no* effort instruction — it is the model's neutral state, *less* steering than sending nothing (absent defaults to `xhigh`). If you consider that a fold rather than a level, declare `[xhigh, low, none]` instead and clients asking `medium` get told the model has no middle tier. Operator's call; both are honest. |
| DeepSeek-V4 profiles | leave unset for now | dsv4 uses its own chat encoder with its own effort profile and validation; declare only after checking which spellings that encoder accepts. |
| `qwen38-nvfp4` / `qwen38-fp8` | measure first | Same probe we ran on Flash-Next: render a fixed conversation at each candidate level, list only the levels that produce distinct prompts (plus `none` if `enable_thinking:false` changes the render). |

## Getting the code

```bash
git clone https://github.com/mardelden/sglang-custom.git && cd sglang-custom
git diff v0.5.18..origin/overlay/reasoning-efforts-v0.5.18 -- python/ > reasoning-efforts.patch
```

**One patch serves both runtimes** (unlike `log-requests-events`, which needs
its own variant per base):

| Runtime | Apply with |
|---|---|
| `stock` (0.5.18 wheel) | `strip=2` into site-packages |
| `qwen4-pr36497` (source tree) | `strip=1` |

3 files, ~105 patch lines, pure Python — no rebuild. Verified to apply to both
bases, in either order relative to the `log-requests-events` patch (they share
`server_args.py`; composition tested in both orders on all three bases).

## Before deploying — one gate still open

The container was **down** when this landed, so the full unit-test run against
its venv is still pending. Run these there first (CPU-only, no GPU needed):

```bash
python -m unittest \
  test.registered.unit.entrypoints.openai.test_serving_chat \
  test.registered.unit.test_server_args_namespaces \
  test.registered.unit.test_runtime_context_config_bags
```

The validator's logic itself is verified (13/13 scenario checks + 7 new unit
tests), but the guardrail suites need the real venv.

## Verify after deploying

```bash
# unlisted level -> 400 naming the list (was: silent fold or template 500)
curl -s -X POST http://<host>:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"x","max_tokens":8,"reasoning_effort":"high",
       "messages":[{"role":"user","content":"hi"}]}'
# expect: 400 "reasoning effort 'high' is not supported by this deployment;
#          supported levels: xhigh, medium, low, none"

# listed level still works
#   ... "reasoning_effort":"xhigh" ...   -> 200
```

## Rollback

Reverse the patch, or simply remove `reasoning_efforts` from the profile — an
unset flag is byte-for-byte stock behaviour.

## Relationship to what is already deployed

Complementary to the `anthropic-effort-400` fix already live on the box: that
one translates the *template's own rejections* into 400s (the backstop); this
one catches the levels the template would **silently fold** before it ever
renders (the front gate). With both, every dishonest path is closed: fold →
400 from the gate, template raise → 400 from the backstop.
