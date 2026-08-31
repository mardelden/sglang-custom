# Decision: SGLang runtimes use a released wheel plus patches; a source build only when no release ships the model

**Status:** Accepted
**Date:** 2026-08-30

> **This is the fork's copy, kept for whoever picks up SGLang next.** The
> operational original is `plans/decisions/044-sglang-wheel-plus-patch-over-source-build.md`
> in `~/src/proxmox`, where the Ansible role that enforces it lives. If the role
> changes and only one copy is updated, **the proxmox one is authoritative** —
> it is the one wired to the machinery.

## Context

The fleet runs two SGLang runtimes on `sglang` (VMID 250), both constrained by sm120:

| Runtime | Install | Serves |
|---|---|---|
| `stock` | `uv pip install sglang==0.5.18` (PyPI wheel), patched in site-packages at `strip=2` | 7 of 9 profiles — all DeepSeek-V4-Flash variants and both Qwen3.8-27B variants |
| `qwen4-pr36497` | source checkout, editable install | 2 profiles — Qwen3.8-Flash-Next |

We now carry a third fix (the Anthropic reasoning-effort 400/500 fix, see the
`sglang-custom` branch log) and had to decide where it lives. That reopened a
broader question: should runtimes build from our fork by default, now that
`mardelden/sglang-custom` mirrors what is deployed?

Two facts decide it.

**A source install is meaningfully more expensive than a wheel install.** The
PyPI wheel ships three prebuilt pyo3 extensions (`_server`, `_grpc`,
`_multimodal` under `sglang/srt/rust_extensions/`). A source install must
compile them, and `setup.py` hard-fails with "cargo is required to discover the
Rust extension modules" long before any Python runs. That means a Rust toolchain
(currently 1.92, pinned by the tree's own `rust/rust-toolchain.toml`) plus
`build-essential`, `pkg-config`, `libssl-dev` and `protobuf-compiler`.

**Only one model actually needs it.** `qwen4_exp` is in no SGLang release —
0.5.18's registry has 244 architectures and this is not one of them, so a stock
server silently resolves it to the transformers fallback (which does not
implement it either) and dies at load. There is no wheel to patch. Every other
model we serve is in the released wheel, where a patch file is sufficient.

## Decision

**Default to the released wheel plus patch files. Treat a source build as an
exception that must be justified by capability, not convenience.**

| Situation | Mechanism |
|---|---|
| The released wheel can serve the model | Wheel install + `.patch` files in `roles/sglang/files/patches/`, applied to site-packages. **Never** convert to a source build to carry a fix. |
| No release ships the model at all | Source build, and only then |
| A source build is unavoidable | Build from a **pinned ref in our fork**, not from a moving `pull/N/head`. Fixes ride as commits on that branch; the runtime's `patches:` list is empty. |

Concretely: `stock` stays a wheel install and keeps
`dsv4-sm120-topk-buckets.patch`. `qwen4-pr36497` stays a source build but now
builds `mardelden/sglang-custom` `runtime/qwen4-pr36497` rather than
`pull/36497/head`, carrying `qsa-sm120-fa4` and the Anthropic effort fix as
commits.

The role supports both shapes: a source runtime takes either `pull_request:` or
`repo:`/`ref:`, and `origin` is re-pointed on every run so a tree cloned from
upstream migrates onto the fork in place.

> **Not landed as of 2026-08-30.** The role change above is written and lint-clean
> but sits on the unmerged, unpushed branch `sglang/build-qwen4-from-fork` in
> `~/src/proxmox`, and has **never been run against the container**. The box is
> still on a shallow checkout of `pull/36497/head` with the fixes hand-applied as
> dirty files. Read the "Decision" section as the agreed target, not as the
> current state. Running it is `just sglang-runtime -e
> sglang_runtime_to_build=qwen4-pr36497`, which re-checks-out `--force` and so
> replaces those hand-edits with the branch content — behaviour-preserving,
> because the two were verified byte-identical.

The fork remains the readable record of every runtime regardless of how it is
installed — `runtime/stock-0.5.18` is `v0.5.18` plus its patch, and is *not* a
build source. That is deliberate: the record and the build mechanism are
different jobs.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Build every runtime from the fork, one mechanism | uniform; fixes always survive a rebuild; no patch-drift | forces Rust + build toolchain onto the runtime serving 7 of 9 profiles; much longer installs; replaces a validated wheel with a tree we build ourselves | large cost, no capability gained — a patch file already does the job for `stock` |
| Keep `qwen4-pr36497` on `pull/36497/head` and add a third patch file | one mechanism everywhere; nothing new to learn | an open PR's head moves, so the deployed commit is whatever the PR was on build day, and a patch can break against a head we did not choose | reproducibility matters more here than mechanism uniformity; the build was already unavoidable |
| Pin `pull_request:` to a specific sha instead of using the fork | reproducible without fork machinery | fixes still have to be re-applied as patches afterwards, so anything the role does not know about is silently lost on rebuild | solves half the problem |
| Mirror the vLLM decision (036) — immutable derived images | strong attestation and rollback story | SGLang here runs as native venvs under systemd, not containers; there is no image pipeline to select from | wrong shape for this deployment; revisit if SGLang moves to containers |

Note the tension with **036-vllm-patch-profile-overlay-ownership**, which
rejects patching site-packages as "not a release mechanism". That holds for
vLLM, where the fleet ships immutable derived images and a bind-mounted overlay
would be unattestable. SGLang here is a native venv install with no image
boundary, so the site-packages patch *is* the release mechanism, applied by
Ansible and idempotent on re-run. The two decisions differ because the
deployment shapes differ, not because the principle changed.

## Consequences

- Adding a fix to a wheel-served model means writing a `.patch`, not migrating
  the runtime. The patch header must name the upstream PR/issue and the
  condition under which it can be dropped, as both existing patches do.
- `stock` never needs a Rust toolchain. Only `qwen4-pr36497` declares
  `rust_toolchain`.
- `qwen4-pr36497` no longer tracks PR #36497 automatically. Taking PR updates is
  now a deliberate rebase of the fork branch, which is the intended trade.
- A rebuild of `qwen4-pr36497` checks out `--force`, so it replaces any hand-edits
  on the box with the branch content. That is the point: the branch is the
  source of truth, and a dirty tree on the container is a bug, not a state.
- `runtime/stock-0.5.18` in the fork must be updated whenever
  `dsv4-sm120-topk-buckets.patch` or the pinned wheel version changes, or it
  stops being an accurate record. It has no automated link to the deployment.
- If SGLang ever moves to containers, revisit against 036.

## References

In this repo:

```
runtime/stock-0.5.18        branch: v0.5.18 + the dsv4 patch, as a readable record
runtime/qwen4-pr36497       branch: what the box actually serves
runtime/unified-0.5.18      branch: both, built but never run on hardware
plans/decisions/001-...     OTel tracing carries no prompt text
```

In the fleet repo (`~/src/proxmox`), owned by the deployment team:

```
roles/sglang/defaults/main.yml         runtime definitions; the rule is restated there
roles/sglang/tasks/runtime_build.yml   source-build path (repo:/ref: or pull_request:)
roles/sglang/tasks/install.yml         wheel path + site-packages patching
roles/sglang/files/patches/            the two sm120 patches
plans/handovers/sglang-usage-and-patches.md   runtime inventory and the pyo3/Rust cost
plans/decisions/036-vllm-patch-profile-overlay-ownership.md   the contrasting vLLM shape
```
