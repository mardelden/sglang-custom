# Deploy: `--log-requests-events` (request-logging volume fix)

**For:** the deployment team · **Written:** 2026-08-31 · **Self-contained** — you
should not need any other document to act on this.

## Why

Full-content request logging currently writes **the prompt three times per
request**. At `--log-requests-level 3`, one OpenAI request emits:

| Event | Contains |
|---|---|
| `request.received.openai` | the raw OpenAI payload, pre-adaptation (level ≥ 2 only) |
| `request.received` | the adapted request — same prompt, different shape |
| `request.finished` | the request **again**, plus the response |

Only the third adds anything new. On the 144k-token contexts we see in
production that is roughly **1.7 MB of duplicated text per request**, and today
there is no way to ask for less without dropping to level 1, which discards
content entirely.

`request.finished` is self-sufficient — it re-serializes the request beside the
response — so selecting only it captures every request/response pair while
writing the prompt once.

## What changes

A new server flag, `--log-requests-events`, defaulting to all three events.
**A deployment that does not set it behaves exactly as today.**

```
--log-requests-events finished
```

That is the whole behavioural change.

**What you give up:** requests that never complete. Today a client disconnect
leaves a `received` line with no matching `finished`; with only `finished`
selected it leaves nothing. If tracking aborts matters, use
`--log-requests-events received finished` instead — still drops the raw-OpenAI
copy, so 2× instead of 3×.

## Getting the code

```bash
git clone https://github.com/mardelden/sglang-custom.git
cd sglang-custom
git diff v0.5.18..origin/overlay/log-requests-events-v0.5.18 -- python/ \
  > log-requests-events.patch
```

**Use that branch, not `feat/log-requests-events`.** Both carry the same change,
but the deployed runtimes predate the runtime-context migration:
`TokenizerManager` reads `self.server_args.log_requests_*` on our bases and
`get_observability().log_requests_*` on current upstream. The `main`-based
variant **fails to apply** on both our runtimes. That is an accessor difference,
not context drift — do not force it through.

### Applies to both runtimes, one patch

| Runtime | Base | Apply with |
|---|---|---|
| `stock` | sglang 0.5.18 wheel | `strip=2` into `site-packages` (drops `a/` and `python/`) — same convention as the two sm120 patches |
| `qwen4-pr36497` | PR #36497 @ `7c66045d7` | `strip=1` into the source tree |

Verified to apply cleanly to **both** bases. 6 files, ~240 patch lines, pure
Python — **no rebuild, no Rust, no sgl-kernel**. Per the wheel-plus-patch policy
this stays a patch; do not convert `stock` to a source build for it.

## Configure

Recommended for capture:

```
--log-requests --log-requests-level 3 --log-requests-format json
--log-requests-target /var/log/sglang-requests
--log-requests-events finished
```

Note `stdout` is **deliberately absent** — see the journald warning below.

### It can be changed without a restart

All request-logging settings, including the new one, are live-toggleable:

```bash
curl -X POST http://<host>:30000/configure_logging \
  -H 'Content-Type: application/json' \
  -d '{"log_requests": true, "log_requests_level": 3,
       "log_requests_format": "json", "log_requests_events": ["finished"]}'
```

This matters: a restart of Flash-Next costs **157 s** of weight load. Use the
endpoint for changes; the flags are only the boot default.

## Two operational traps

### 1. Do not point logrotate at the live file

SGLang uses `TimedRotatingFileHandler(when="H", backupCount=0)` — it rotates
**itself**, hourly, to `{base}.YYYY-MM-DD_HH`, and `backupCount=0` means
**nothing is ever deleted**. It rotates forever and prunes nothing.

Adding logrotate on the *active* file breaks it either way:

- default `create` mode — logrotate renames the file, Python keeps writing to
  the renamed one through its open fd, the new file stays empty. Silent loss.
- `copytruncate` — Python keeps its byte offset, so after truncation it writes
  past the end, producing a sparse file padded with NULs.

**Instead, prune the already-rotated files**, which are closed and safe:

```bash
find /var/log/sglang-requests -name '*.log.20??-??-??_??' -mtime +7 -delete
```

A systemd timer, or a logrotate stanza globbing **only** the rotated pattern.

### 2. The journal is not a usable archive for this

If `stdout` is in `--log-requests-target`, that copy goes to journald, which:

- **rate-limits by default** — `RateLimitIntervalSec=30s`, `RateLimitBurst=10000`.
  Under load it silently *drops* messages.
- **caps line length at `LineMax`, default 48K.** Our prompts serialize to
  ~575 KB per line and will be **truncated**.

So the journal copy is lossy and truncated while the file copy is complete, and
you pay to write both. Drop `stdout` from the target list for capture.

## Verification already done

Against the **deployed base** (PR #36497 @ `7c66045d7`) using the container's own
venv:

- 26 guardrail tests green — `test_server_args_namespaces`,
  `test_runtime_context_config_bags`, `test_global_config_read_ratchet`,
  `test_server_args_mutation_ratchet`
- 185 `server_args` tests and 10 config ratchets green on the upstream variant
- functional: `["finished"]` emits only `request.finished`; the default emits
  all events; the raw-OpenAI gate is correctly False at level 1

## Rollback

Reverse the patch and restart:

```bash
git apply -R log-requests-events.patch    # or patch -R for site-packages
systemctl restart sglang
```

Or simply stop passing `--log-requests-events` — the default is every event,
i.e. today's behaviour. The flag is the only thing that changes anything.

## Upstream status

**Not yet submitted.** This is a general improvement rather than a local quirk,
so it should go upstream and be dropped from our carried set once accepted.
Until then it is a permanent local divergence and needs re-applying after any
wheel upgrade — `ansible.posix.patch` is idempotent, so a re-run on an
already-patched tree is a no-op.
