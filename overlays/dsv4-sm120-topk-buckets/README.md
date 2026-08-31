# dsv4-sm120-topk-buckets

Pads non-instantiated sparse-MLA topk widths on sm120 instead of crashing.

**Commit:** `866c002c78` · **Files:** `python/sglang/kernels/ops/attention/flash_mla_sm120.py`

## What it prevents

DSpark's draft indexer emits `topk=192`. CUTLASS sm120 sparse-MLA is instantiated
only for `{128, 512, 1024}` decode and `{128, 512, 1024, 2048}` prefill, so verify
falls through to the prefill kernel and hits its `num_tokens > 64` assert — which
speculative verify can never satisfy, since it submits `batch × (γ+1)`.

**Without this, DeepSeek-V4 + DSPARK cannot boot on sm120 at all.** It dies during
draft CUDA-graph capture, i.e. *after* a full weight load.

The fix right-pads the index tensor with `-1` (the kernels' documented skip
sentinel) up to the next instantiated bucket and caps the scan via `topk_length`,
so normal decode keeps the CUTLASS fast path and only the odd draft width is padded.

## Do not take the documented workaround

`SGLANG_SM120_FLASHMLA_BACKEND=triton` boots, but routes *all* sparse-MLA through
Triton including hot-path decode. Measured on 2× RTX PRO 6000 Blackwell:
C=1 101.0 → 119.6 (+18%), **C=16 1188.4 → 248.7 (−79%)**.

## Applicability

- **Applies to stock `upstream/main`:** yes, verified.
- **Prerequisite:** none.
- **Activates:** unconditionally, on sm120. Not gated — without it the server
  does not start on this hardware, so there is no working default to preserve.
- **Composes with:** `anthropic-effort-400`, `log-requests-events` (disjoint
  files, verified in any order).

## Remove when

Upstream [sgl-project/sglang#33407](https://github.com/sgl-project/sglang/pull/33407)
merges, or flashinfer instantiates `topk=192`
([flashinfer#4309](https://github.com/flashinfer-ai/flashinfer/pull/4309) — closed
unmerged as of 2026-08-28, so not imminent).
Fixes [sgl-project/sglang#33985](https://github.com/sgl-project/sglang/issues/33985).

## Extract

```bash
git show 866c002c78 -- python/ > dsv4-sm120-topk-buckets.patch
```

Do **not** use `git diff $(git merge-base upstream/main runtime/stock-0.5.18)..runtime/stock-0.5.18`:
this branch is a deployment snapshot based on the `v0.5.18` release branch, so that
diff sweeps in ~14 files of unrelated release-branch churn alongside the one file
that is ours.
