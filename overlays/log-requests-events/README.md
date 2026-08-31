# log-requests-events

Adds `--log-requests-events` so request-logging can emit only the events you want.

**Commit:** `c417f8e154` · **Files:** `server_args.py`, `utils/request_logger.py`,
`managers/tokenizer_manager.py`, `managers/io_struct.py`, `managers/configure_logging.py`,
`entrypoints/openai/serving_base.py`

## The problem

At `--log-requests-level 3` the prompt is serialized **three times** per OpenAI
request:

| Event | Contains |
|---|---|
| `request.received.openai` | the raw OpenAI payload, pre-adaptation (level ≥ 2 only) |
| `request.received` | the adapted request — same prompt, different shape |
| `request.finished` | the request **again**, plus the response |

On a 144k-token context that is roughly **1.7 MB of duplicated text per request**,
and there was no way to ask for less without giving up content entirely by dropping
to level 1.

`request.finished` is self-sufficient — it re-serializes the request beside the
response — so `--log-requests-events finished` captures every request/response pair
while writing the prompt once.

## The trade

You lose requests that never complete. Today a client disconnect leaves a
`received` line with no matching `finished`; with only `finished` selected it
leaves nothing at all.

## Two implementation details worth knowing

- **Only the emission is gated** in `log_received_request`. The `input_ids → obj.text`
  decode that follows it still runs unconditionally, because `request.finished`
  re-serializes `obj` and would otherwise lose its text for input_ids-only requests
  whenever the received event is disabled.
- **The `level >= 2` rule for `request.received.openai` is load-bearing**, not
  cosmetic, and now lives in `RequestLogger.should_log_openai_received()` beside the
  event check. Unlike the other two events that path does not apply `skip_names`, so
  emitting it at level 0/1 would leak exactly the content those levels exist to redact.

## Applicability

- **Applies to stock `upstream/main`:** yes, verified.
- **Prerequisite:** none.
- **Activates: only when the flag is passed.** The default is all three events, so a
  deployment that sets nothing behaves exactly as before. This is the one carried set
  that is genuinely off by default.
- **Live-toggleable:** plumbed through `ConfigureLoggingReq`, so it can be changed over
  `POST /configure_logging` with no restart — which matters on models with long weight
  loads (157 s for Flash-Next).

## Verification

Run against the deployed venv: 185 `server_args` tests, 24 NS-coverage guardrails
(`test_server_args_namespaces`, `test_runtime_context_config_bags`), 10 config
ratchets, plus a functional check that `["finished"]` emits only `request.finished`
and that the OpenAI gate is False at level 1 and False when the event is deselected.

## Remove when

Accepted upstream, or superseded. Worth upstreaming — the 3× reduction is a general
win, not a local quirk.

## Extract

```bash
BASE=$(git merge-base upstream/main feat/log-requests-events)
git diff $BASE..feat/log-requests-events -- python/ > log-requests-events.patch
```
