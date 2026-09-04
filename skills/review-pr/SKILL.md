---
name: review-pr
description: Adversarial two-model review of a PR or branch. One model reviews as the counterpart of whoever authored the diff, the other model tries to refute every blocking finding, and only sustained findings reach the human. Read-only; emits a machine-parseable VERDICT block.
allowed-tools: Bash(git:*), Bash(gh:*), Bash(ls:*), Bash(cat:*), Bash(head:*), Bash(tail:*), Bash(wc:*), Bash(grep:*), Bash(rg:*), Bash(find:*), Bash(claude:*), Bash(codex:*), Bash(mktemp:*), Bash(date:*), Bash(which:*)
---

# /review-pr

**Arguments:** `$ARGUMENTS` — `[<PR-number-or-branch>] [task:<url-or-id>] [spec:<path>] [context:<path>] [exchange:<path>] [as-counterpart] [lens:<name>] [panel] [no-verify] [claude-model:<id>] [codex-model:<id>]`

- `<PR-number-or-branch>` (optional) — resolve it yourself when
  omitted: `gh pr list --head "$(git branch --show-current)"`, else
  the current branch.
- `task:<url-or-id>` (optional) — the ticket, issue, or task this
  change implements (GitHub issue URL/number, ClickUp/Jira/Linear
  URL). Its text is the **scope statement** (step 2).
- `spec:<path>` (optional) — a file holding the scope statement,
  when there is no ticket or the ticket is unreachable.
- `context:<path>` (optional) — a file the driver wrote for the
  reviewer: PR title/body, CI status, scope statement, default
  branch (step 0b.2). Lets the reviewer run fully offline.
- `exchange:<path>` (optional) — prior-round objections and driver
  responses, present when this is round ≥ 2 (step 4).
- `as-counterpart` (optional token) — present when the driver
  delegated this invocation; pins you to the reviewer role (step 0a).
- `lens:<name>` (optional token) — narrow the review to one lens from
  the table below, at full depth. Without it, run the standard
  checklist (step 3).
- `panel` (optional token) — driver-side escalation: fan out one
  review per lens across both models, adversarially verify findings,
  merge (step 0b). Auto-escalates when the scope statement or diff
  touches auth, tenancy, payments, or secrets.
- `no-verify` (optional token) — skip adversarial verification of
  blocking objections (step 0b.4). Cheaper, noisier.
- `claude-model:<id>` / `codex-model:<id>` (optional tokens) — pin
  the model each CLI uses. See *Models* below.

## Models

Two harnesses, two models. Each CLI takes a model flag:

- Claude → `claude -p --model <id>` (aliases like `fable`, `opus`,
  `sonnet`, or a full id such as `claude-fable-5-1`).
- Codex → `codex exec -m <id>`.

Resolution order, per harness: argument token → environment
(`REVIEW_PR_CLAUDE_MODEL`, `REVIEW_PR_CODEX_MODEL`) → the CLI's own
configured default. Write the resolved pair into the review header
and the context file so every verdict records which models judged
it.

**Interactive confirmation (driver only, step 0b.1).** Before the
first delegation, print the plan on one line and ask once:

```
Review plan: reviewer = codex (gpt-5.x) · verifier = claude (fable) · lenses = standard checklist
Use these, or change? [enter to accept | e.g. "codex-model:gpt-5.6 panel"]
```

Headless (`-p`/`exec`, no TTY, or `as-counterpart`): skip the
question, print the plan line, proceed.

## Lenses

Each lens is a full-depth review of ONE dimension. A focused pass
finds what an omnibus checklist glosses.

| Lens | Hunt for |
|------|----------|
| `correctness` | Trace every changed code path end to end. Inputs, states, or call orders that produce wrong behavior. Every new parameter actually applied — accepted-but-unused arguments are the canonical miss. Off-by-one on boundaries, wrong identifier passed, condition inverted, error swallowed. |
| `security` | Tenancy: is every fetched entity bound to the caller's org/account, or only gate-checked? Cross-tenant reads and writes. AuthZ checked at the route but not enforced in the query. Identifier injection through path/query params. Secrets in logs or responses. Unvalidated input reaching a strict check (string `"false"` passing a `=== false` guard). |
| `test-adequacy` | Mutation-style: if each fixed bug returned, would any test fail? Do tests reach the code under test, or pass at an earlier gate (mocked-away, short-circuited)? Missing negative cases (foreign tenant, empty set, expired state, concurrent writer). Assertions on outcomes vs on status codes alone. |
| `runtime` | N+1 queries, sync I/O in async paths, unbounded materialization of result sets or files, missing timeouts or retries, partial writes without a transaction, behavior at 10× data volume. |
| `standards` | The step 3 blocking checklist verbatim — scope, test depth, dead code, repo conventions, code standards, comment discipline. |

With `lens:<name>`, run only that lens and tag every objection with
it: `1. [blocking] [correctness] …`. Verdict format is unchanged.

## Role

You are the **reviewer** in a two-agent exchange. Another agent (the
driver) — or a human — implemented a change and is asking whether it
holds up before it merges. The reviewer is always the counterpart of
whichever model authored the diff: Codex authored it → Claude
reviews; Claude authored it → Codex reviews. A human authored it →
either reviews, and the other verifies.

Your session is fresh; the scope statement, the diff, the context
file, and the exchange file are the entire shared context. The
driver, not you, talks to the user — anything you need from a human
travels back as data in the verdict.

Typical invocations (both headless):

- Driver is Claude →
  `codex exec --sandbox read-only --skip-git-repo-check -m <model> -o <verdict-file> 'Use $review-pr on <branch-or-PR> as-counterpart context:<path> [exchange:<path>]'`
- Driver is Codex →
  `claude -p "/review-pr <branch-or-PR> as-counterpart context:<path> [exchange:<path>]" --model <model> --output-format text`

The reviewer needs **no network** when a context file is supplied:
the driver fetched the base branch and captured PR metadata and CI
status into that file (step 0b.2). That is what makes a read-only
sandbox safe for the Codex side. Without a context file, Codex needs
`--sandbox workspace-write -c 'sandbox_workspace_write.network_access=true'`
(both flags; dropping only `--sandbox read-only` still leaves it
without network), and the no-mutation guarantee is then the *Refuse
to* rule alone.

## What you do

### 0. Determine your role

Three cases, checked in order:

**a. Arguments contain the token `as-counterpart`** — you are the
reviewer, invoked headless by the driver. Proceed to step 1 and never
delegate back (this token exists to make the hand-off terminate). If
you somehow authored the diff anyway, still review, with the
`SELF-REVIEW` note rule below. If the diff was authored by your own
model in a *different* session (a commit trailer or the context file
names your model, but this session wrote nothing), review normally
and make the first `NOTES` line `SAME-MODEL: fresh session — shared
model blind spots possible; cross-model verification still binding`.

**b. You authored the diff** — this session wrote it, the branch
commits carry a trailer naming your model (`Co-Authored-By: Claude …`
/ `Codex …`), or the user says so. **Never guess from absence:**
trailers are optional, and assuming authorship when it is merely
unknown can delegate the review back to the model that actually
wrote the code. If authorship is genuinely unknown, ask the user when
interactive; when headless, act as reviewer instead, with the first
`NOTES` line `DEGRADED: authorship unverified — counterpart guarantee
not established`. When you did author it, you are the **driver** —
self-review removes the one property this exchange exists to provide,
so do not review; **delegate and relay**:

1. **Plan.** Preconditions: the change must be committed and pushed.
   If it isn't, say so and stop — preparation (commits, pushes, PR
   creation, suite runs) is driver work that happens outside this
   skill; re-invoke once pushed. A PR is not required: a pushed
   branch reviews via `git diff origin/<default>...<branch>`.
   Resolve the models (*Models* above) and the gate shape: `panel`
   token, or a scope statement / diff touching auth, tenancy,
   payments, or secrets, means the panel escalation below rather
   than the single call in item 3. Print the plan line; confirm it
   with the user when interactive.
2. **Context file.** Write one file *outside* the repo (`mktemp -d`)
   so the reviewer can run offline and sandboxed:
   ```
   # review-context
   default_branch: <name>            # gh repo view --json defaultBranchRef
   base_sha: <sha of origin/<default>>
   head_sha: <sha of the branch tip>
   authored_by: <claude|codex|human|unknown> (<how you know>)
   models: reviewer=<harness>/<model> verifier=<harness>/<model>
   ci: <gh pr checks summary, or "no PR">
   ## PR
   <gh pr view --json title,body — or "no PR">
   ## Scope statement
   <ticket text / spec file / PR body, and which one it is>
   ## Repo conventions
   <path(s) of CLAUDE.md / AGENTS.md / CONTRIBUTING.md present>
   ```
   Run `git fetch origin <default> --quiet` first so the diff base is
   current.
3. **Delegate.** From the repo root, run the counterpart yourself and
   wait for it (invocations under *Role*). Pass `context:<path>` and,
   from round 2, `exchange:<path>`.
4. **Verify adversarially** (skipped only with `no-verify`). For every
   `[blocking]` objection in the verdict, ask the model that did NOT
   raise it, headless, writing nothing:
   `"Adversarially verify this review finding against the diff on
   branch <branch> (base <default>). Default to REFUTED unless the
   evidence holds up. Reply SUSTAINED or REFUTED, then one paragraph
   citing file:line: <objection>"`.
   Sustained objections stay `[blocking]`; refuted ones move to
   `NOTES` with the refutation. The gate is `AGREE` if and only if
   zero objections survive. A verifier that errors leaves the
   objection `[blocking]` with the note `unverified`.
5. **Relay.** The verdict block is at the end of the counterpart's
   output (or in the `-o` file). Relay the merged block to the user
   **verbatim** — it is the counterpart's judgment, not yours to
   soften — and surface each `QUESTIONS-FOR-USER` item as a question
   to answer now.
6. If the counterpart CLI is missing, errors, or returns no
   `VERDICT:` line, the gate **failed to run** — report exactly that
   (never treat it as an AGREE), and offer a labeled self-review as
   the explicit fallback.
7. After fixes, re-invoke the same way with an exchange file carrying
   each prior objection and your response — that is round 2.
   Maximum 3 rounds, then present both positions to the user.
8. When the gate completes (final `AGREE`, user arbitration, or an
   explicit stop), close with a **gate summary** — shown to the user
   and, when a PR exists and the user asked for it, posted as one PR
   comment beneath the verdict. Its job is to make the gate's value
   legible to a teammate who never opens the diff. Shape and order:
   - **Headline catch first** — the single highest-impact finding as
     one sentence of consequence ("a rebase silently ate the version
     bump; no client would ever have updated"), never a rule
     citation. Skip when nothing was found.
   - **Scorecard** — real defects fixed · false alarms that reached a
     human · findings refuted before reaching a human · human
     decisions needed · wall clock · who authored / who reviewed /
     who verified, with models (and lenses, for a panel).
   - **Findings ranked by blast radius**, one line each, outcome
     first: `fixed in <commit> — <what was wrong, phrased by its
     consequence>`, or `rebutted — <why, and that the reviewer
     accepted it>`.
   - Questions the user answered, and what they decided.
   - Close with the cost line: the invocations and roughly how long
     this run took.
   - A round-1 `AGREE` with nothing found reports exactly that plus
     elapsed time — a cheap clean pass is also the system working.

**Panel escalation (thorough bug hunt).** When the arguments carry
`panel`, or the change touches auth/tenancy/payments/secrets, replace
the single counterpart call in 0b.3 with the lens fan-out:

1. Pick the lens set — a fixed floor plus content-driven additions:
   - **Always:** `correctness` and `test-adequacy`.
   - Auth, tenancy, payments, secrets, or user-controlled identifiers
     in the diff: add `security`.
   - Diff touches queries, async paths, loops over data, bulk I/O, or
     multi-row writes: add `runtime`.
   - Repo has no deterministic lint covering its conventions: add
     `standards`.

   Additions only — never shrink the floor. The author choosing
   which scrutiny to skip is exactly the bias this gate exists to
   remove.

   Run the set in parallel where your harness allows, all with
   `as-counterpart` and the same `context:` file. Cross-model
   diversity goes to the judgment-heavy lenses: counterpart model
   takes `correctness`, `security`, `standards`; your own model in a
   fresh session (`claude -p` if you are Claude, `codex exec` if you
   are Codex) takes `test-adequacy` and `runtime`.
2. Verify every `[blocking]` objection exactly as in 0b.4, with the
   model that did NOT raise it.
3. Merge into ONE verdict block you relay to the user: sustained
   objections stay `[blocking]` (keep their lens tags and note which
   model raised each); refuted ones move to `NOTES` with their
   refutation; questions and notes are unioned. The gate is `AGREE`
   if and only if zero objections survive verification.
4. Rounds: after fixes, re-invoke only the lenses whose objections
   were sustained, each with the exchange file. Maximum 3 rounds,
   then present both positions to the user.
5. Counterpart CLI unavailable: still run your own model's fresh-
   session lenses (they carry the `SAME-MODEL` note), skip
   verification for findings only one model can see, and make the
   merged verdict's first `NOTES` line
   `DEGRADED: counterpart unavailable — cross-model lenses missing`.
   Never present a degraded panel as the full gate.

The default (no `panel`, no sensitive surface) stays the single
full-checklist counterpart call plus per-objection verification —
the cheap path for routine diffs.

**c. Neither** — the user is asking you to review work someone else
authored. You are the reviewer; proceed to step 1. When interactive
and the other harness's CLI is on PATH, offer to run the verify pass
(0b.4) on your own blocking objections before emitting the verdict.

**User override / SELF-REVIEW rule:** if the user explicitly insists
you review your own diff, run it — but the first `NOTES` line must
read `SELF-REVIEW: authored by this agent — independence absent;
counterpart review still owed`, and the verdict never substitutes
for the counterpart's.

### 1. Resolve the diff

Prefer the context file when present — it is the driver's snapshot
and needs no network. Otherwise:

```bash
gh repo view --json defaultBranchRef -q .defaultBranchRef.name   # or: git symbolic-ref refs/remotes/origin/HEAD
git fetch origin <default> --quiet
git diff origin/<default>...<branch>        # or: gh pr diff <N>
gh pr checks <N>                             # CI status, when a PR exists
gh pr view <N> --json title,body             # PR title/description, when a PR exists
```

Review the **merge-base diff** (`...`), not the two-dot diff — the
review surface is what would land, not the branch tip vs a stale
base. A change may span several PRs on one branch; review the branch
union or a single PR as it opens, cite the CI of whatever you
reviewed, and say which it was in the verdict's `NOTES`.

### 2. Re-derive the scope

The **scope statement** is the first of these that exists:

1. `spec:<path>` file.
2. `task:<url-or-id>` — `gh issue view <N> --json title,body` for
   GitHub issues; for other trackers use a reachable tool (MCP,
   CLI) or the copy in the context file. Unreachable → `DEGRADED`.
3. The PR description.
4. The commit messages on the branch.

Say which one you used in `NOTES`. You judge the diff against what
the scope statement and the repo's own conventions say, not against
the PR description's claims about itself. Read every convention file
the repo carries (`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, a
`docs/` standards page it points to) — its rules are binding where
they say "must"/"never"/"always".

### 3. Judge

This is a **static review**. Do not run test suites — cite CI for
pass/fail; your job is what CI cannot see.

With `lens:<name>` in the arguments, run the named lens from the
Lenses table instead of the checklist below — one dimension, full
depth, objections tagged with the lens. Without a lens, the
checklist below is the review.

Before judging, **enumerate the attack surface**: list every changed
entry point (route, handler, job, exported function, migration,
config key) and, for each, write down three ways it could fail. Then
go looking for those failures in the code. This is the adversarial
step; a review that skips it grades the diff on what it says instead
of what it does.

`[blocking]` findings:

1. **Scope** — the diff implements the scope statement and nothing
   unrelated. Drive-by refactors, cross-module changes, and churn in
   files outside the change's purpose are blocking.
2. **Correctness** — every changed code path traced end to end;
   every new parameter, flag, or config key actually applied; no
   inverted condition, off-by-one, wrong identifier, or swallowed
   error. A behavior change with no caller that exercises it is a
   finding.
3. **Test depth** — tests call a real entry point with realistic
   preconditions and assert business outcomes. Structure-only checks
   (`hasattr`, `callable`, source inspection,
   status-code-without-body, snapshot of a mock) do not count and are
   blocking. For every bug this change fixes: would the test fail if
   the bug returned?
4. **Dead code** — every new service, hook, component, or module is
   imported from a production path, not only from its own test (grep
   the source tree; the repo's convention file may name the exact
   check).
5. **Repo conventions** — the binding rules in the repo's convention
   files: test layout, changelog entries, doc updates that must ship
   with an endpoint change, traceability markers, commit format.
   Cite the rule.
6. **Code standards** — the language-agnostic non-negotiables: strict
   layer boundaries (thin handlers, logic in services), typed inputs
   and outputs at every boundary, enums over magic strings, domain
   errors over framework errors, no N+1 queries, no sync I/O in async
   code, no magic values, no phantom edge cases, multi-row writes
   that must change together wrapped in a transaction.
7. **Comment discipline** — no ticket references, change narration,
   or "what the next line does" comments in code.

Advisory findings (report under `NOTES`, never block):

- Naming, structure, or simplification suggestions.
- Coverage still missing from the scope statement after this change
  (partial deliveries may ship; carryover just needs to be visible).
- Commit-message and PR-title format, unless the repo makes it a
  rule.

### 4. Rounds ≥ 2 — converge, don't loop

When an exchange file is supplied, it carries your earlier objections
and the driver's response to each. For every one, either:

- **Accept** — the revision or rebuttal resolves it; drop it.
- **Maintain** — restate with **new evidence or a new argument**;
  verbatim repetition is forbidden.

Raise new objections only against content that changed since the
round you reviewed. Do not sandbag: everything visible in round 1
must be objected to in round 1.

### 5. Emit the verdict

This contract binds the **reviewer's** output. (The driver relays the
block verbatim, then follows with the gate summary — 0b.8; ends-at-
the-verdict does not apply to the driver's relay.) As reviewer, your
final message ends with exactly this block — nothing after it:

```
VERDICT: AGREE | REVISE
MODELS: reviewer=<harness>/<model> [verifier=<harness>/<model>]
OBJECTIONS:
1. [blocking] <file:line> — <what is wrong> — <concrete input or state → wrong result> — <rule or scope line it violates>
2. ...
QUESTIONS-FOR-USER:
1. <question only a human can answer, if any>
NOTES:
- <non-blocking observation, if any>
```

- `VERDICT:` starts the line, appears exactly once. The driver parses
  it mechanically.
- `AGREE` if and only if there are zero `[blocking]` objections.
- Every objection carries a **failure scenario** — the concrete
  input, state, or call order that produces the wrong result. An
  objection without one is a note, not a blocker: the verifier
  cannot refute what cannot fail.
- Empty sections may be omitted, except `VERDICT:` itself.

**Degraded mode:** if the scope statement, `gh`, or the base branch
is unreachable, review what you can reach and make the first `NOTES`
line `DEGRADED: <what failed>` so the driver reports the gate as
degraded rather than passed.

## Rules

- **Judge the change; never author a rival implementation.** Say what
  is wrong and what evidence shows it — the driver owns the fix.
- One severity only: `[blocking]` per the checklist above; everything
  else is a note.
- Pre-existing violations in untouched code are out of scope — the
  diff is the review surface. Mention truly dangerous ones as notes.
- Skip anything a formatter or linter would catch.

## Refuse to

These bind the **reviewer** role (steps 0a/0c → 1–5). The driver path
(0b) necessarily runs the counterpart CLI, writes the context and
exchange files outside the repo, and may post the final verdict +
gate summary as a PR comment when the user asks — that is its job —
but mutates nothing else: no commits, pushes, merges, approvals, or
tracker transitions.

- Review a diff you authored without the explicit user override —
  delegate to the counterpart per step 0 instead.
- Write anything into the checkout under review. The reviewer runs in
  the worktree holding the diff and nothing enforces this but the
  rule, so "helpfully" fixing what you found silently edits the
  branch under review — the one thing a reviewer must never do.
- Prepare a diff for review under this skill: no commits, pushes, PR
  creation, or suite runs to make it reviewable — that is driver work
  done outside, before re-invoking.
- Mutate anything: no commits, pushes, PR comments, approvals, merges,
  tracker transitions, or file writes.
- Run test suites or linters that write to the workspace.
- Wait for, or address, the user directly.
- Emit a response without the verdict block, or with prose after it.
- Return `AGREE` on a scope you could not read — unless the failure
  is declared via `DEGRADED`.

## Hand-off

None. The verdict block is the whole deliverable; the driver parses
it and runs the next round, fixes findings, or proceeds to close.
