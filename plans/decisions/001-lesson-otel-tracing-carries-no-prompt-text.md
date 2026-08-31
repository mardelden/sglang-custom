# Lesson: SGLang's OTel tracing carries no prompt text — content only comes from request logging

**Date:** 2026-08-30
**Area:** ai / sglang / observability

## What We Were Trying to Do

Capture every client request and response from the inference servers, starting with
SGLang, and land it somewhere queryable. The fleet already runs SigNoz (`signoz:4317`
OTLP) and Langfuse, and Langfuse is the LLM-specific store that wants prompts, tokens
and cost — so the obvious move was to turn on SGLang's OpenTelemetry export and point
it at the collector.

## What Happened

SGLang has `--enable-trace` / `--otlp-traces-endpoint`, which looks exactly like the
right knob. It is not, for this purpose: **the spans contain no prompt or completion
text at all.**

Reading `python/sglang/srt/observability/trace.py`, the `SpanAttributes` class is the
OTel GenAI semantic-convention set and nothing more:

```
gen_ai.usage.{prompt,completion,cached}_tokens
gen_ai.request.{max_tokens,top_p,top_k,temperature,n,id}
gen_ai.response.{model,finish_reasons}
gen_ai.latency.{time_in_queue,time_to_first_token,e2e,
                time_in_model_prefill,time_in_model_decode,time_in_model_inference}
```

Token counts, sampling parameters, finish reasons, latency breakdown. No message
bodies. Turning on tracing and expecting Langfuse to fill with prompts produces
gen_ai spans with the content missing — and nothing errors, so it looks like it worked.

A second, quieter trap sits next to it: `--log-requests-level` **defaults to 2**, which
is documented as "metadata, sampling parameters and *partial* input/output". Enabling
request logging without setting the level therefore captures truncated prompts, which
is worse than not capturing them, because the archive looks complete.

## Root Cause

The two subsystems answer different questions and were built for different consumers.

Tracing answers *"what did this request cost and where did the time go"* — it is aimed
at APM backends and deliberately follows the OTel GenAI semconv, which treats message
content as optional and privacy-sensitive. Request logging answers *"what was actually
said"* and is a separate code path (`RequestLogger`, driven from `TokenizerManager`)
that never touches the tracer.

Nothing in the flag names signals this. `--enable-trace` reads like it subsumes
request logging; it does not overlap with it at all.

## Solution

Three mechanisms exist. Pick by what you need, not by what sounds most modern.

| Need | Mechanism |
|---|---|
| Prompt + completion **content** | `--log-requests --log-requests-level 3 --log-requests-format json --log-requests-target <dir>` |
| Latency, tokens, cost, trace shape | `--enable-trace --otlp-traces-endpoint signoz:4317` |
| Bulk forensic capture | `dump_requests_folder` + `dump_requests_threshold` — batched **pickle**, not JSON |

Notes that matter in practice:

- **`--log-requests-target` takes multiple targets**, `stdout` and/or directory paths:
  `--log-requests-target stdout /var/log/sglang/requests`. Combined with
  `--log-requests-format json` this gives a structured on-disk stream to ship.
- **`/configure_logging` (GET/POST) toggles all of it live** — `log_requests`,
  `log_requests_level`, `log_requests_format`, the dump folder and threshold, and
  `log_level` — with **no restart**. On Flash-Next a restart costs 157 s of weight
  load, so this is the difference between a 1-second change and a 3-minute outage.
  `python -m sglang.srt.managers.configure_logging` wraps it.
- **SGLang extracts inbound `traceparent` / `tracestate`** (`TRACE_HEADERS`), so it
  already satisfies point 4 of the instrumentation contract in `infra:observability`:
  a client that propagates W3C context gets its SGLang spans stitched onto the same
  trace without any further work.
- Transport is **gRPC by default**; `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf`
  switches to HTTP. SGLang passes only `endpoint=` to the exporter and lets the SDK
  read auth from `OTEL_EXPORTER_OTLP_TRACES_HEADERS`, so a direct export to Langfuse
  is *probably* reachable that way — **untested**, and it would still carry no prompt
  text, so it solves the smaller half of the problem.

## How to Avoid in Future

- **Do not assume an LLM server's OTel export includes prompts.** The GenAI semconv
  makes content optional and most servers omit it. Check the span attributes before
  designing around it.
- **Always set `--log-requests-level` explicitly.** The default silently truncates.
- **Use `/configure_logging` rather than editing the unit** for anything log-related
  on this model. A restart is 157 s.
- Budget for volume and retention before enabling level 3. Real traffic on Flash-Next
  has been observed at **144k cached tokens on a single request** — full-prompt capture
  at that size is not a rounding error, and it is plain-text user content on disk.

## Still Open

The wider question is whether capture belongs **per-engine** or at a **single
gateway** in front of all engines. The fleet runs ollama, llamacpp and seven
vllm-* endpoints besides sglang, and engine-side support is very uneven — so
per-engine capture means several schemas and several things to re-check on every
upgrade.

As of 2026-08-30 the fleet repo is being wired **per-engine** (sglang, llamacpp
and vllm each getting their own flags), which answers it in practice. That work
is not ours and was still uncommitted when this was written, so treat the above
as the trade-off it accepted rather than as an open question. Two gaps worth
tracking against it: nothing uses `/configure_logging`, so changing capture
level costs a restart; and there is **no log rotation**, with plaintext prompts
growing unbounded.

## Related

In this repo (paths are repo-relative, and the branches carry what we deploy):

```
python/sglang/srt/observability/trace.py            SpanAttributes, TRACE_HEADERS
python/sglang/srt/managers/configure_logging.py     the live-toggle client
python/sglang/srt/server_args.py                    the --log-requests-* / --enable-trace flags
runtime/qwen4-pr36497                               branch: what the box serves
```

In the fleet repo (`~/src/proxmox`) — cross-repo, and owned by the deployment
team rather than by us:

```
plans/decisions/044-sglang-wheel-plus-patch-over-source-build.md   runtime/patch policy
plans/handovers/sglang-usage-and-patches.md                        runtime inventory
plans/107-sglang-serving.md                                        measurement log
roles/sglang/templates/sglang.service.j2                           where the flags get set
```

Fleet observability contract: `~/.claude/skills/infra--observability/`
(SigNoz `signoz:4317`, Langfuse, Beyla).
