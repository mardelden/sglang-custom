# plans/

Our notes on operating this fork.

These live on `main`, which is otherwise a clean mirror of `upstream/main`. The
fork convention allows docs-only files there — it is code on `main` that turns
every upstream sync into a merge conflict, not markdown. Keeping them here means
they are visible to anyone who lands on the fork, rather than hidden on a branch
nobody thinks to check.

Per-patch-set documentation does **not** live here — it lives in
`overlays/<name>/README.md` on the branch carrying that set, so that composing
two sets can never collide on one path. `DEPLOYMENT-BRANCHES.md` at the repo
root indexes them.

```
decisions/    numbered decisions and lessons, newest number wins
```

Wider fleet documentation — container inventory, benchmark logs, deployment
policy — lives in `~/src/proxmox/plans/` and belongs to the deployment team.
Anything here should be about SGLang itself.

## Index

| | |
|---|---|
| `decisions/001-lesson-otel-tracing-carries-no-prompt-text.md` | `--enable-trace` captures no prompts; content only comes from `--log-requests` at level 3 |
| `decisions/002-wheel-plus-patch-over-source-build.md` | Patch the released wheel; a source build needs a capability justification. Fork copy — the operational original lives in `~/src/proxmox` |
