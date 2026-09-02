# anthropic-effort-400

Forwards Anthropic reasoning effort unchanged, and reports the template's own
rejections as **400** instead of 500. The **coupled partner** of
`reasoning-efforts` — do not deploy that gate without this.

**Commit:** `40f7ae1178` · **Files (code):**
`python/sglang/srt/entrypoints/anthropic/serving.py`
· **Tests:** `test/registered/unit/entrypoints/anthropic/test_serving.py`

## What it fixes

1. **`xhigh` was rewritten to `max`** on the false premise that the OpenAI
   Literal lacks `xhigh` (it does not). The rewrite converted the one tier
   Qwen3.8-Flash-Next supports into one it rejects.
2. **Template `raise_exception` surfaced as 500**, not 400. Both Anthropic
   handlers caught the OpenAI layer's client-error `ValueError` with a bare
   `except Exception` and replaced it with "Internal server error", discarding
   a message that names the accepted values. Nine `raise_exception` sites, not
   just effort.

## Why it is COUPLED to `reasoning-efforts` — keep both

The `reasoning-efforts` gate runs in `_process_messages`; the stock
`xhigh→max` rewrite runs in the Anthropic adapter **before** it. Without this
patch, a client's `xhigh` is laundered to `max` upstream of the gate, so the
gate sees only `max`:

- vocabulary lists `xhigh` → gate rejects the laundered `max` → client gets a
  400 naming a value they never sent
- vocabulary lists `max` → gate accepts silently → the exact fold the gate
  exists to prevent

Neither is honest. The gate can only be honest on the value that *reaches* it,
and this patch is what stops the value being rewritten first. **Remove this and
the gate actively breaks `xhigh`.**

## Applicability — BOTH runtimes

- **Applies to stock `upstream/main` and `v0.5.18`:** yes, verified.
- **No prerequisite.** The bug is in the stock Anthropic serving layer, not in
  PR #36497 — that PR only supplies the model that surfaces it. **stock also
  needs it:** Qwen3.8-27B (served by `stock`) ships the same
  `('xhigh','medium','low')` template guard and the same fold.
- **One code-only patch (88 lines) applies to both deployed bases** — `v0.5.18`
  and PR #36497 @ `7c66045d7`. Verified.
- **Not gated** — a bug fix behind a flag would leave the broken path default.

## Deployment note — the patch is code-only; run the gate on the branch

The vendored patch for production carries `serving.py` **only** (no test files
in site-packages). The test additions therefore do **not** travel with it, so
running a code-only-patched *PR-vintage tree's* own tests fails on fixture skew
(`_MockTokenizerManager` predates the change). That is a test-methodology
artifact, not a code defect. **Gate against this branch in a worktree** (code +
tests + fixtures consistent), the way the other overlays are verified — not by
patching a stale tree and running its stale suite.

## Verification

61/61 anthropic unit tests green (the two new 400 tests + the rewritten
forward-unchanged matrix). Measured on Qwen3.8-Flash-Next, both surfaces:
`minimal/high/max 500→400`, `xhigh 500→200`, `low/medium 200→200`.

## Remove when

Fixed upstream. This half is a genuine stock bug (the false-premise comment)
and is the strongest upstream candidate of the carried set — but per operator
decision (2026-09-01) it stays a carried fork patch for now, matching the
llamacpp posture.

## Extract

```bash
# deployment (either runtime), code only
git diff v0.5.18..overlay/anthropic-effort-400-v0.5.18 -- python/ > anthropic-effort-400.patch
# upstreaming (code + tests)
git diff $(git merge-base upstream/main feat/anthropic-effort-400)..feat/anthropic-effort-400 > anthropic-effort-400.patch
```
