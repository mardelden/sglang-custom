# anthropic-effort-400

Forwards Anthropic reasoning effort unchanged, and reports bad tiers as 400 rather
than 500.

**Commit:** `40f7ae1178` · **Files:** `python/sglang/srt/entrypoints/anthropic/serving.py`,
`test/registered/unit/entrypoints/anthropic/test_serving.py`

## What it fixes

Two independent defects made four of the six Claude-protocol effort levels return
HTTP 500 against Qwen3.8-Flash-Next — including the level the model defaults to.

1. **`xhigh` was rewritten to `max`**, on the stated grounds that "the OpenAI Literal
   does not include the Anthropic-only xhigh". `ReasoningEffortTier` has included
   `xhigh` for some time, so the premise no longer holds and the rewrite converted
   the one tier this model supports into one it rejects.

2. **A client error was reported as a server error.** `_convert_to_internal_request`
   raises `ValueError` for faults the OpenAI layer has already diagnosed as the
   caller's — chat-template `raise_exception` chief among them, converted there
   *specifically* so the calling surface can answer 400, which `/v1/chat/completions`
   does. Both Anthropic handlers caught it with a bare `except Exception` and
   replaced it with 500 `"Internal server error"`, discarding a message that names
   the accepted values.

**This is not effort-specific.** The Qwen3.8-Flash-Next chat template has **nine**
`raise_exception` sites — system message containing an image, message roles out of
order, no user query found, and so on — and every one of them returned 500 on this
surface.

## Measured, before → after

On Qwen3.8-Flash-Next (2× RTX PRO 6000 Blackwell, TP=2), both streaming and
non-streaming:

```
minimal  500 → 400        low     200 → 200
high     500 → 400        medium  200 → 200
max      500 → 400        xhigh   500 → 200
```

## Applicability

- **Applies to stock `upstream/main`:** yes, verified.
- **Prerequisite:** none. The bug is in the stock Anthropic serving layer, not in
  PR #36497 — that PR only supplies the model that surfaces it.
- **Activates:** unconditionally. **Not gated**, deliberately: putting a bug fix
  behind a flag would leave the broken path as the default.
- **Composes with:** `dsv4-sm120-topk-buckets`, `log-requests-events` (disjoint
  files, verified in any order).

## Remove when

Fixed upstream. **This belongs in an upstream PR** — it is a stock upstream bug
affecting nine error paths on any model whose template validates, not a local
quirk, and carrying it permanently is the wrong end state.

## Note on the non-streaming handler

The original non-streaming `try` wrapped *generation* as well as conversion. A
blanket `ValueError → 400` there would have mislabelled genuine server faults as
client errors, so the block is split first: conversion gets the 400, generation
keeps its unchanged 500. The streaming path was already scoped correctly.

## Extract

```bash
git show 40f7ae1178 -- python/ > anthropic-effort-400.patch
```
