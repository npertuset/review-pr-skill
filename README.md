# review-pr — adversarial two-model PR review

A Claude Code / Codex skill that reviews a pull request or branch with
**two models working against each other**:

1. The model that did *not* write the diff reviews it (the counterpart).
2. Every blocking finding is handed to the *other* model with orders to
   refute it. Only findings that survive reach a human.
3. The driver relays a machine-parseable `VERDICT:` block plus a short
   gate summary (headline catch, scorecard, findings by blast radius).

It is read-only by contract: the reviewer never commits, pushes,
comments, or edits the checkout under review.

Works from either side — invoke it in Claude Code (`/review-pr`) and it
shells out to `codex exec` for the counterpart, or invoke it in Codex
(`$review-pr`) and it shells out to `claude -p`.

## Install

```bash
git clone git@github.com:npertuset/review-pr-skill.git ~/.review-pr-skill
~/.review-pr-skill/install.sh
```

The installer symlinks `skills/review-pr` into `~/.claude/skills/` and
`~/.codex/skills/`, so `git pull` in the clone updates both. Run it
with `--copy` instead if you prefer a snapshot, and `--uninstall` to
remove the links.

To install into a single repo instead of your user profile:

```bash
mkdir -p <repo>/.claude/skills
cp -r ~/.review-pr-skill/skills/review-pr <repo>/.claude/skills/
```

## Runtime dependencies

- `git`, and `gh` (GitHub CLI, logged in) for PR metadata and CI status.
- `claude` (Claude Code CLI) and/or `codex` (OpenAI Codex CLI), each
  logged in on its subscription. One is enough to run a single-model
  review; both are needed for the adversarial exchange. The skill
  declares `DEGRADED` when the counterpart CLI is missing rather than
  pretending the gate passed.

## Usage

```
/review-pr                              # PR for the current branch, standard checklist
/review-pr 1793                         # a PR number
/review-pr feat/foo task:https://app.clickup.com/t/abc123
/review-pr 1793 spec:./docs/spec.md     # scope statement from a file
/review-pr 1793 panel                   # one review per lens, both models, verified, merged
/review-pr 1793 lens:security           # one lens at full depth
/review-pr 1793 claude-model:fable codex-model:gpt-5.6
/review-pr 1793 no-verify               # skip the refutation pass (cheaper, noisier)
```

Before the first delegation the driver prints its plan and asks once:

```
Review plan: reviewer = codex (gpt-5.x) · verifier = claude (fable) · lenses = standard checklist
Use these, or change?
```

Set `REVIEW_PR_CLAUDE_MODEL` / `REVIEW_PR_CODEX_MODEL` in your shell to
change the defaults for every run; argument tokens override them for
one run.

## What "scope" means here

The reviewer judges the diff against a **scope statement**, resolved in
this order: `spec:` file → `task:` ticket/issue → PR description →
commit messages. It records which one it used. Repo convention files
(`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`) are binding where they
say "must"/"never"/"always".

## The verdict contract

```
VERDICT: AGREE | REVISE
MODELS: reviewer=codex/gpt-5.6 verifier=claude/fable
OBJECTIONS:
1. [blocking] src/x.ts:42 — <what is wrong> — <input/state → wrong result> — <rule violated>
QUESTIONS-FOR-USER:
1. <only a human can answer>
NOTES:
- <non-blocking>
```

`AGREE` if and only if zero `[blocking]` objections survive. Every
objection must carry a concrete failure scenario; without one it is a
note. Orchestrators (see `docs/roadmap.md`) can parse `VERDICT:` and
`OBJECTIONS:` directly.

## Layout

```
skills/review-pr/SKILL.md   the skill (same file serves Claude Code and Codex)
install.sh                  symlink/copy into ~/.claude/skills and ~/.codex/skills
docs/roadmap.md             design notes and planned improvements
```
