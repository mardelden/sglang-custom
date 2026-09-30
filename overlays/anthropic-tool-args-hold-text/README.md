# anthropic-tool-args-hold-text

Stops the Anthropic `/v1/messages` streaming adapter from dropping the tail
of a tool call's arguments (usually the closing `}`) in multi-tool turns.

**Cause.** Tool-call parsers can emit the separator between two calls (for
`qwen3_coder`, the `"\n"` after `</tool_call>`) as `delta.content` *before*
they flush the first call's last argument fragment. The adapter opened a text
block for that text, which closed the open `tool_use` block; the late fragment
then hit the "no open tool_use block" branch and was dropped. The client gets
invalid JSON, rejects the call, and the model retries (a full extra model
call). The last call of a turn is never affected. `/v1/chat/completions` and
`/v1/responses` are immune: their clients accumulate arguments by tool index.

**Fix.** While a `tool_use` block is open, text deltas are held instead of
closing the block. Held text is released before the next block of any kind
opens and at end of stream, so it keeps its position; whitespace-only held
text is dropped (a real Anthropic stream never carries it as a block).

- **Files:** `python/sglang/srt/entrypoints/anthropic/serving.py`, plus two
  regression tests in `test/registered/unit/entrypoints/anthropic/test_serving.py`.
- **Activates:** always, on streaming `/v1/messages` only. No flag. Streams
  without text inside a tool call are byte-identical to before.
- **Variants:** `feat/anthropic-tool-args-hold-text` (main-vintage; also the
  PR #37253 vision tree) and `overlay/anthropic-tool-args-hold-text-v0.5.18`
  (stock wheel). Never cross vintages.
- **Evidence (2026-09-30, ct250, Qwen3.8-27B-FP8, qwen3_coder):** prod journal
  had 38 `Dropping tool_call argument delta ...: '}'` warnings in 7 days, all
  exactly `'}'`. Six real multi-tool streams from the loaded model, converted
  by both adapters: stock 6/14 calls invalid JSON, patched 0/14. Adapter unit
  suite 61/61 with the patch; both new tests fail on the unpatched adapter.
- **Upstream:** not fixed as of `53225fadf4` (2026-09-30) — the drop branch is
  unchanged. Related: #39782 (closed, no linked fix), #29410 (same whitespace
  class at the DeepSeek parser layer, closed unmerged).
- **Remove when:** upstream stops closing an open `tool_use` block on text,
  or routes late argument fragments by tool index.

## Checking a container (no rebuild, nothing installed)

Both scripts run with the serving venv on the SGLang host itself:

- `ab_adapter.py` — **before deploying.** Captures real multi-tool streams from
  the running engine once, then replays the identical bytes through the
  installed adapter and through a patched tree put first on `PYTHONPATH`. It
  needs no restart and no GPU memory beyond serving the captures.
- `verify_live.py` — **after the restart.** Sends Claude-Code-shaped multi-tool
  requests to `/v1/messages` and checks that every `tool_use` input parses.
  Pair it with the journal: no new `Dropping tool_call argument delta`
  warnings since the restart.

Baseline on ct250 before the fix (2026-09-30): `verify_live.py` found 5/14
calls invalid; `ab_adapter.py` found 3/7 on the installed adapter and 0/14 on
the patched tree.
