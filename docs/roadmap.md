# Design notes and roadmap

## What changed from the original

The skill started life inside a workspace with a Jira tracker, a
requirements repo, and a traceability CLI. Generalizing it meant:

- The primary argument is now the PR or branch, not a ticket key. The
  ticket is optional (`task:`), and the **scope statement** falls back
  to a spec file, the PR body, then commit messages.
- Traceability markers and coverage-tool checks are gone as blocking
  items. They survive only as "repo conventions" — if a repo's
  `CLAUDE.md`/`AGENTS.md` demands markers, that rule is binding because
  the repo says so, not because the skill does.
- The base branch is resolved from the remote, not hard-coded.
- Model selection is explicit (`claude-model:` / `codex-model:`,
  environment defaults, interactive confirmation of the plan).
- Adversarial verification of blocking findings is now the **default**
  for every driver-side run, not only the `panel` escalation.
- The driver writes a **context file** outside the repo (scope, PR
  metadata, CI, SHAs, models) so the counterpart can run in a
  read-only sandbox with no network.
- Every objection must carry a concrete failure scenario. Without one
  the verifier has nothing to refute, so it is downgraded to a note.
- A mandatory "enumerate the attack surface" step precedes the
  checklist: list every changed entry point and three ways each could
  fail, then hunt for those.

Three blockers raised by a Codex counterpart review of the first
commit, all sustained and fixed:

- `install.sh --uninstall` deleted whatever directory sat at the
  target. It now only removes a symlink into this clone or a copy
  carrying its marker file, and reports anything else.
- A degraded review could still emit `VERDICT: AGREE`, which an
  orchestrator reading only that line would take as a pass. The block
  now carries a required `STATUS: COMPLETE | DEGRADED` line; a gate
  passes only on `AGREE` and `COMPLETE`. `REVIEWED: base= head=` pins
  the SHAs so a stale verdict can be rejected.
- Convention files were read from the branch under review, so a PR
  could rewrite the rules it was judged by. Conventions now load from
  the base SHA, author-controlled text (PR body, commits, comments,
  diff, exchange responses) is declared evidence rather than
  instructions, and a diff that edits a convention file is a scope
  finding.

## review-plan

Added as a sibling skill so a plan can go through the same exchange
before any code exists. Design choices, and why:

- **The plan is a file with a fixed skeleton**, and every codebase
  assumption carries a `file:line`. That turns a prose-vs-prose
  argument into something the reviewer can check by opening files.
- **The driver owns the plan; the reviewer never writes a rival one.**
  Two models each proposing full plans do not converge. Objections
  plus one-line remedies do.
- **Blocking has a closed definition** (uncovered requirement, step
  the code cannot support, broken ordering, untested step, irreversible
  step without rollback, convention violated). Anything else is a
  note, which is what stops the two models from bikeshedding.
- **No separate verifier by default.** In `review-pr` a third session
  refutes findings because the driver must not judge its own code.
  Here the driver's rebuttal is the refutation and the reviewer must
  accept or maintain with new evidence. `verify` turns the extra pass
  back on.
- **HTML is rendered, never generated.** `render.py` is a
  dependency-free converter so the shareable artifact costs zero model
  tokens. Markdown stays the source of truth.
- The agreed plan feeds `/review-pr <branch> spec:<plan>` so the
  implementation is judged against what both models signed.

## Planned improvements

1. **Structured output alongside the prose block.** Emit a JSON twin
   of the verdict (`{verdict, models, objections:[{file,line,claim,
   scenario,rule,lens,raised_by,verified_by,status}]}`) so
   orchestrators stop regex-parsing markdown. Keep the prose block for
   humans.
2. **Diff-size guard.** Above a configurable line count, refuse the
   single-call path and require `panel`, or split the review by file
   group and merge. Large omnibus reviews are where misses cluster.
3. **False-alarm ledger.** The gate summary already reports refuted
   findings; persist a per-model tally (raised / sustained / refuted)
   in `~/.review-pr/stats.jsonl` so you can see which model
   over-reports on which lens and tune the lens assignment.
4. **Author detection helper.** A tiny script that inspects commit
   trailers and branch prefixes (`ai/`, `codex/`, `claude/`) and prints
   `authored_by`, so the driver never guesses.
5. **Test-mutation hints.** For each `[blocking] [test-adequacy]`
   objection, ask the reviewer to name the one-line mutation that
   would slip past the suite. The driver can optionally apply it in a
   throwaway worktree and run the single test file to confirm — the
   only place the gate is allowed to execute tests, and never in the
   checkout under review.
6. **Third harness.** The adapter pattern is two lines per CLI; add
   Gemini CLI or a local model as a third verifier for tie-breaks when
   rounds hit the cap.
7. **PR-comment posting as an opt-in flag** (`post`), using one
   comment per gate rather than per round, with the `MODELS:` line
   visible so readers know who judged.
8. **review-plan: exchange-only HTML view.** Render the review exchange
   as a collapsible per-round table (objection · lens · outcome) next
   to the plan instead of appending it as raw Markdown.
9. **review-plan: plan diff in the reviewer prompt as a unified diff
   with context**, plus a `changes-only` token that restricts round ≥ 2
   reviews to changed sections mechanically rather than by rule.

## Fit with squirrel-agent

squirrel-agent's GitHub-native review (`src/review/prDebate.ts`) runs a
two-model *debate* and posts the result as a `🤖` PR comment. The
recommended integration is to make squirrel-agent call this skill for
each reviewer (`claude -p "/review-pr <branch> as-counterpart
context:<file>"`, `codex exec ... '$review-pr ...'`) and parse the
`VERDICT:` / `OBJECTIONS:` block instead of its own `AGREED:` line. One
review contract, shared by the interactive and automated paths, and
the debate loop becomes the skill's per-objection verification pass.
