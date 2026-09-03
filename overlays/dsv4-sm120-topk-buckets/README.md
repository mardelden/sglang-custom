# dsv4-sm120-topk-buckets (main-vintage variant)

Pads non-instantiated sparse-MLA topk widths on sm120 to the next kernel
bucket (-1 skip sentinel, scan capped via `topk_length`) and routes
decode-sized batches the CUTLASS decode kernel cannot serve to the Triton
fallback. Without it DeepSeek-V4 + DSPARK cannot boot on sm120 — it dies
during draft CUDA-graph capture.

- **Files:** `python/sglang/kernels/ops/attention/flash_mla_sm120.py` (only)
- **Activates:** unconditionally, on sm120 (no-ops elsewhere: probe paths
  only run for `d_qk==512` decode-sized dispatch).
- **Variants:** this branch (`feat/dsv4-sm120-topk-buckets`, main-vintage —
  the vision runtime `dsv4-vision-pr37253` uses this one); v0.5.18 variant is
  commit `866c002c78` on `runtime/stock-0.5.18`. Never cross vintages.
- **flashinfer compat:** works with released flashinfer 0.6.x (private
  `_decode_dsv4_dispatchable` probe) AND with flashinfer >= PR #4802 (falls
  back to the public `supported_sparse_mla_sm120_configs()` API — the PR
  removed the private predicate). PR-4802 flashinfer is what fixes sm120
  image prefill for DSV4-Vision (dual-cache runtime topk), so the vision
  runtime is expected to run the PR build.
- **Remove when:** upstream sgl-project/sglang#33407 merges, or a flashinfer
  release ships the PR-4802 continuous decode envelope AND sglang's tree
  stops probing the old predicate. Re-evaluate the whole patch then: under
  PR-4802 the decode envelope is continuous (any H in [1,128], topk >=
  min_topk), which likely makes the bucket padding itself unnecessary.

Extraction (per fork convention — diff against the branch base, never
`upstream/main`):

    BASE=$(git merge-base upstream/main feat/dsv4-sm120-topk-buckets)
    git diff $BASE..feat/dsv4-sm120-topk-buckets -- python/ > dsv4-sm120-topk-buckets-main.patch
