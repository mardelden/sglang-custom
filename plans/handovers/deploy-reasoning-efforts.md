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

## Per-profile vocabularies — measured, ready to paste

Every Qwen profile below shares **one byte-identical chat template** (8952 bytes:
`Qwen3.8-27B-FP8`, `Qwen3.8-27B-NVFP4`, and `Qwen3.8-Flash-Next-FP8` are the same
file), so they get the same vocabulary. Verified against the actual templates,
not inferred from the family name.

```yaml
# All five Qwen profiles:
sglang_profiles:
  qwen38-fp8:            { reasoning_efforts: [xhigh, medium, low, none] }
  qwen38-nvfp4:         { reasoning_efforts: [xhigh, medium, low, none] }
  qwen38-flash-next-fp8:         { reasoning_efforts: [xhigh, medium, low, none] }
  qwen38-flash-next-fp8-sharded: { reasoning_efforts: [xhigh, medium, low, none] }
```

| Profile | `reasoning_efforts` | Basis |
|---|---|---|
| `qwen38-fp8` | `[xhigh, medium, low, none]` | template guard `('xhigh','medium','low')`; `none` valid — `enable_thinking:false` pre-closes the think block (line 165) |
| `qwen38-nvfp4` | `[xhigh, medium, low, none]` | template byte-identical to the above |
| `qwen38-flash-next-fp8` | `[xhigh, medium, low, none]` | same template; effects measured live earlier |
| `qwen38-flash-next-fp8-sharded` | `[xhigh, medium, low, none]` | same weights, same template |
| **DeepSeek-V4 profiles (all 5)** | **leave UNSET** | see below — do **not** guess |

**The `medium` caveat still stands** for all Qwen profiles: `medium` passes the
guard but injects *no* effort instruction — it is *less* steering than sending
nothing (absent defaults to `xhigh`). If you consider that a fold rather than a
tier, declare `[xhigh, low, none]` instead and a client asking `medium` is told
the model has no middle tier. Both are honest; it is your call.

### Why DeepSeek stays unset — and why guessing is worse than leaving it

The DeepSeek profiles do **not** use a Jinja template — they use the `dsv4` chat
encoder, which has its *own* effort vocabulary and its *own* validation:

```
preview  profile: {high, max}          (default: high)
official profile: {low, high, max}     (default: low)
```

Which profile `deepseek-ai/DeepSeek-V4-Flash-0731` resolves to is detected from
the encoder file *inside the checkpoint* (`chat_encoding.py` inspects
`DEFAULT_REASONING_EFFORT` / `REASONING_EFFORT_PROMPTS`) — I could not read it
because the container is down. Declaring the wrong set is actively harmful: list
`[high, max]` on a checkpoint that is really `official` and you reject a `low`
the encoder would have honored. And dsv4 disables thinking via a separate
`thinking_mode` switch, not `reasoning_effort='none'`, so the `none` semantics do
not map. Determine the profile from the live checkpoint first, then set exactly
that set. Until then, unset = the encoder's own validation still applies (it
already rejects unknown levels), so nothing is lost by waiting.

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
