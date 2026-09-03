# Carried changes in this fork

`main` is a clean mirror of `upstream/main` and carries no code — only this
catalogue. It is never rebased or deleted, so it is where anyone consuming this
fork should land first.

**This file is an index.** Where it disagrees with a patch set's own manifest,
the manifest wins.

## Patch sets

The atomic unit is the **patch set**, not the branch. Each is independently
applicable; extract one against *its own base*, never against `upstream/main`:

```bash
BASE=$(git merge-base upstream/main <branch>)
git diff $BASE..<branch> -- python/ > overlay.patch
```

| Patch set | Commit | Files | Applies to stock `upstream/main`? | Scope | Off by default? |
|---|---|---:|---|---|---|
| `dsv4-sm120-topk-buckets` | `866c002c78` | 1 | **yes** | host-specific — sm120 only | no (correctness fix) |
| `dsv4-sm120-topk-buckets` *(main variant)* | branch `feat/dsv4-sm120-topk-buckets` | 1 | **yes** (incl. PR #37253 tree) | host-specific — sm120; the vision runtime's copy | no |
| `qsa-sm120-fa4` | `09dc961d6a` | 1 | **no** — see prerequisite | host+model — sm120 × Flash-Next | no (correctness fix) |
| `anthropic-effort-400` | `40f7ae1178` | 2 | **yes** | fleet-wide (**stock too** — 27B shares the fold) | no (bug fix) |
| `anthropic-effort-400` *(overlay pair)* | branches `feat/anthropic-effort-400` + `overlay/…-v0.5.18` | 2 | one code-only patch → `v0.5.18` **and** `7c66045d7` | fleet-wide | no |
| `log-requests-events` | `c417f8e154` | 6 | **yes** | fleet-wide | **yes** — defaults to all events |
| `log-requests-events` *(v0.5.18 backport)* | `e553971e5c` | 6 | n/a — targets `v0.5.18` | fleet-wide | **yes** |
| `reasoning-efforts` | `e5b5939ecc` | 3 | **yes** | fleet-wide | **yes** — unset flag = passthrough |
| `reasoning-efforts` *(v0.5.18 backport)* | branch `overlay/reasoning-efforts-v0.5.18` | 3 | applies to `v0.5.18` **and** `7c66045d7` | fleet-wide | **yes** |
| `responses-error-cause` | branch `feat/responses-error-cause` (+ v0.5.18 overlay) | 1 | one patch → `v0.5.18` **and** `7c66045d7` | fleet-wide (/v1/responses) | no (bug fix) |
| `reapply-28035-dsv4-args` | vendored file `overlays/reapply-28035-dsv4-args/` (no branch — main already has it) | 1 | **no** — PR #37253 trees only (`1ca94a0c10`) | vision runtime; upstream's own #28035 hunk, reverted by the vision commit | no (bug fix) |

Verified, not assumed: the sets touch disjoint files **except**
`server_args.py`, shared by `log-requests-events` and `reasoning-efforts` —
their composition is verified instead: every order applies cleanly on
`upstream/main`, `v0.5.18`, and `7c66045d7`.

### `dsv4-sm120-topk-buckets` — on `runtime/stock-0.5.18` + `feat/dsv4-sm120-topk-buckets`
Pads non-instantiated sparse-MLA topk widths. Without it DeepSeek-V4 + DSPARK
cannot boot on sm120 at all — it dies during draft CUDA-graph capture.
*Activates:* unconditionally, on sm120.
*Remove when:* upstream sgl-project/sglang#33407 merges, or flashinfer
instantiates topk=192 (flashinfer#4309, closed unmerged as of 2026-08-28).
*Main variant* (branch `feat/dsv4-sm120-topk-buckets`, 2026-09-03): the
formerly patch-file-only `-main` copy, now carried as a branch. Adds a
flashinfer >= PR #4802 compatibility fallback (the PR removes the private
`_decode_dsv4_dispatchable` predicate this patch probes; the branch falls
back to the public `supported_sparse_mla_sm120_configs()` API). PR-4802
flashinfer is the sm120 image-prefill fix for DSV4-Vision, so the vision
runtime runs this variant. See `overlays/dsv4-sm120-topk-buckets/README.md`
on the branch.

### `qsa-sm120-fa4` — on `runtime/qwen4-pr36497`
Routes QSA varlen decode to SGLang's own SM12x FA4 entry point instead of the
pip `flash_attn.cute` kernel, which dies in warmup with a cutlass MLIRError.
**Prerequisite: PR #36497.** Its target file
`python/sglang/srt/layers/attention/qwen_sparse_attn_backend.py` does not exist
on stock upstream, so this set cannot be applied standalone — it is only
meaningful on a tree that already carries the qwen4 model support.
*Remove when:* sgl-project/sglang#36531 is fixed upstream.

### `anthropic-effort-400` — on `runtime/qwen4-pr36497`
Stops the Anthropic adapter rewriting `output_config.effort: xhigh` to `max`,
and returns 400 with the template's real message instead of a 500 for any
conversion `ValueError`. Fixes nine `raise_exception` sites, not just effort.
*Remove when:* fixed upstream. **This is a stock upstream bug and belongs in an
upstream PR** — it is not a local quirk, and carrying it permanently is the
wrong end state.

### `reasoning-efforts` — on `feat/reasoning-efforts` (+ `overlay/reasoning-efforts-v0.5.18`)
Operator-declared effort vocabulary (`--reasoning-efforts`), enforced at the
one point every client surface converges. Honor verbatim or reject with a 400
naming the declared levels — never remap, never let the template's fold decide.
`none` in the list = the model can genuinely disable reasoning; absent = disable
requests are rejected rather than silently ignored. Implements the fleet's
per-profile `reasoning_efforts` contract (reference rendering: `roles/llamacpp`).
*Deploying it:* `plans/handovers/deploy-reasoning-efforts.md`.
*Caveat:* full unit-test run on the container's venv still pending — it was down
at land time; the manifest lists the exact suites to run first.
*Remove when:* accepted upstream.

### `log-requests-events` — on `feat/log-requests-events`
Adds `--log-requests-events` so `request.received` / `request.received.openai`
can be suppressed, leaving only `request.finished`, which already carries the
request *and* the response. At level 3 this takes a 144k-token prompt from being
written three times (~1.7 MB) to once.
*Activates:* only when the flag is passed — the default is all three events, so
a deployment that sets nothing behaves exactly as before.
*Remove when:* accepted upstream, or superseded.
*Deploying it:* `plans/handovers/deploy-log-requests-events.md`. Note the
deployed runtimes need the **`overlay/log-requests-events-v0.5.18`** variant —
the `main`-based one does not apply to either, because `TokenizerManager` reads
`self.server_args.*` there and `get_observability().*` on current upstream.

## Deployment snapshot branches (not overlays)

These are **not** patch sets and should not be treated as such. They record what
a given runtime actually runs, pinned at the upstream point it was built from,
so a rebuild is reproducible. Diffing one against `upstream/main` sweeps in
unrelated upstream churn — `runtime/stock-0.5.18` shows 15 changed files under
`python/` against its merge-base, of which exactly **one** is ours.

| Branch | Base | Contains |
|---|---|---|
| `runtime/stock-0.5.18` | `v0.5.18` | + `dsv4-sm120-topk-buckets` |
| `runtime/qwen4-pr36497` | PR #36497 @ `7c66045d7` | + `qsa-sm120-fa4` + `anthropic-effort-400` |
| `runtime/unified-0.5.18` | `v0.5.18` | + the 2 qwen4 commits + all three patch sets |

`runtime/unified-0.5.18` is **built and statically verified but has never run on
hardware.** It puts qwen4 on 47 commits it has not been tested against. Treat it
as a candidate, not a release.

`v0.5.18` and the qwen4 PR head **diverge** — common ancestor `861eca8e25`, with
the PR head carrying only 2 squashed commits while `v0.5.18` carries 47. The
qwen4 commits cherry-pick onto `v0.5.18` with **0 conflicts** but onto current
`upstream/main` with **14**, which is why `unified` is anchored at 0.5.18.

## Documentation layout

| Where | What |
|---|---|
| `DEPLOYMENT-BRANCHES.md` (this file, `main`) | the index — every carried set, its scope and removal condition |
| `plans/` (`main`) | decisions and lessons about operating this fork |
| `plans/handovers/` (`main`) | self-contained notes handed to the deployment team |
| `overlays/<name>/README.md` (on the branch carrying the set) | the per-set manifest — **authoritative where it disagrees with this index** |

Per-set docs deliberately do not live at the repo root: two sets would write the
same path with different content and collide the moment they are composed. A
directory per set is disjoint by construction and travels with the branch.

## Caveats

**The fork is not what runs.** The serving container builds a *shallow checkout
of `pull/36497/head`* with fixes hand-applied as dirty files — not this fork. An
Ansible change to repoint it exists but is unmerged and has never been run.
Confirm what the running artifact contains before concluding a fix is deployed.

**Three of the four sets are not gated.** `log-requests-events` is opt-in;
the other three change behaviour unconditionally. For the two sm120 kernel fixes
that is unavoidable — without them the server does not boot on that hardware.
For `anthropic-effort-400` it is a deliberate choice: gating a bug fix behind a
flag would leave the broken path as the default.
