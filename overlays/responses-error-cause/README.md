# responses-error-cause

Stops `/v1/responses` appending a stray `None` to error messages that have no
exception cause.

**Commit:** `feat/responses-error-cause` · **File:**
`python/sglang/srt/entrypoints/openai/serving_responses.py` (one hunk)

## The bug

The responses preprocessing error handler built its message as
`f"{e} {e.__cause__}"` **unconditionally**. Any exception raised on that path
without a `from` clause has `__cause__ is None`, so `str(None)` → `"None"` is
appended and reaches the client verbatim:

```
reasoning effort 'medium' is not supported by this deployment;
supported levels: low, high, max, none None
                                      ^^^^
```

- **Pre-existing on stock `v0.5.18`** — not introduced by any fork patch.
- **Broader than effort:** the `except (ValueError, TypeError, RuntimeError,
  jinja2.TemplateError)` block catches every causeless error on the responses
  surface. The `reasoning-efforts` gate is just a clean trigger (its
  `ValueError` names the levels and carries no cause).
- **`/v1/responses`-only.** The other three surfaces (OpenAI top-level,
  count-tokens, Anthropic) build their messages differently and were already
  clean — which is why the battery, covering those three, missed it. It is the
  wire every Codex client uses (`wire_api = "responses"`).

## The fix

Fold the cause in only when there is one; otherwise `str(e)`. Wrapped errors
(e.g. a template error with a real `__cause__`) still surface their cause.

## Applicability

- Applies to stock `upstream/main` and `v0.5.18`; **one patch to both deployed
  bases** (`v0.5.18` + `7c66045d7`), verified.
- No prerequisite; independent of the other patch sets (different file).
- Not gated — a bug fix.

## Composes with

`reasoning-efforts` (the gate that surfaces it), disjoint files. Deploy both if
you serve Codex/responses traffic against a strict effort vocabulary.

## Verification

Static + simulated: causeless → clean message, with-cause → cause preserved.
**Live curl reproduction pending a restart** — dsv4 is on the stock runtime and
patching it means a weight reload; not done unprompted. Post-fix check:
```
curl -sS -X POST http://<host>:30000/v1/responses -H 'Content-Type: application/json' \
  -d '{"model":"<m>","input":"hi","max_output_tokens":16,"reasoning":{"effort":"medium"}}'
# expect: "...supported levels: low, high, max, none"   (no trailing None)
```

## Remove when

Accepted upstream. Strong PR candidate — a plain bug (appends "None" to error
strings) with no design surface.

## Extract

```bash
git diff v0.5.18..origin/overlay/responses-error-cause-v0.5.18 -- python/ > responses-error-cause.patch
```
