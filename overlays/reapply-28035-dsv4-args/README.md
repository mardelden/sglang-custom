# reapply-28035-dsv4-args (PR-37253 trees only)

Re-applies the `encoding_dsv4.py` hunk of upstream fix #28035
(`265202cda2`), which the DeepSeek-V4-Flash-Vision commit `1320a81168`
in PR #37253 reverted by syncing the file from the checkpoint's bundled
(pre-fix) encoder.

**Symptom without it:** every assistant tool_call in history renders as a
single DSML parameter literally named `arguments` (the encoder's
wrap-on-parse-failure fallback fires because `serving_chat`'s
`normalize_assistant_tool_call_arguments` hands it a dict); the model
imitates the wrapped shape, so tool-call arguments gain one nesting layer
per round trip — deterministic, breaks multi-step agent sessions.

- **Patch content:** byte-for-byte `git show 265202cda2 -- \
  python/sglang/srt/entrypoints/openai/encoding_dsv4.py`. Not our code.
- **Base:** the PR #37253 tree (`1ca94a0c10`). NOT applicable to `main` /
  release trees — they already contain #28035 (a main-based branch would be
  empty, which is why this set is a vendored patch file, not a branch).
- **Verified:** applies clean at `1ca94a0c10`; offline encoder test renders
  dict AND JSON-string args as correct per-key parameters; malformed args
  raise `ValueError` (clean 400) instead of wrapping.
- **Remove when:** the vision runtime rebuilds from any base where the
  vision code is merged on top of #28035.
