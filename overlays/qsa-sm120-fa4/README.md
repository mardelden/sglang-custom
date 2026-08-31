# qsa-sm120-fa4

Routes QSA varlen decode to SGLang's own SM12x FA4 entry point on sm120.

**Commit:** `09dc961d6a` · **Files:** `python/sglang/srt/layers/attention/qwen_sparse_attn_backend.py`

## What it prevents

`_resolve_trtllm_sparse_decode()` gates on `is_sm100_supported() or is_sm121()`, so
sm120 gets `None` and falls through to `_resolve_flash_attn_varlen_func()`. That
imports `flash_attn.cute.interface` from the pip wheel, compiles a generic/SM100
CUTE kernel, and dies in warmup on the QSA varlen shape with a cutlass `MLIRError`
about weakly-congruent coords.

The fix checks SM12x first and uses SGLang's own `flash_attention_v4_sm120` entry
point, mirroring the selection already made in `flashattention_backend.py`.

## Applicability — read this before extracting

- **Applies to stock `upstream/main`: NO.** Verified: the target file
  `python/sglang/srt/layers/attention/qwen_sparse_attn_backend.py` **does not exist**
  on stock upstream. `git apply` fails with *No such file or directory*.
- **Prerequisite: PR #36497** (the `qwen4_exp` / Qwen3.8-Flash-Next model support).
  This set is only meaningful on a tree that already carries it.
- **Activates:** unconditionally, on sm120 with Flash-Next. Not gated — without it
  the server dies in warmup.
- **Composes with:** the other sets (disjoint files), but only on a tree that
  satisfies the prerequisite above.

## Remove when

[sgl-project/sglang#36531](https://github.com/sgl-project/sglang/issues/36531) is
fixed upstream, or PR #36497 lands with sm120 handled.

## Extract

```bash
git show 09dc961d6a -- python/ > qsa-sm120-fa4.patch
```
