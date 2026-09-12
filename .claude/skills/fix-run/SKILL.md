---
name: fix-run
description: The standing protocol for a broken pipeline run — gather forensics, state what ended the run, then fix exactly one deadlock. Use when the user types "FIX RUN" or "WHY RUN", hands over a broken run with no other detail, or asks what ended the newest run. Covers the run_forensics evidence pack, the terminal-vs-non-terminal marker reading, and the stop-and-ask conditions before any code is written.
---

# `FIX RUN` — the standing protocol

> **Why this file is in the blind-triage repo.** `blind-triage/SKILL.md` cites §2b–2c four times for
> *which instrument to run at which boundary, and why*, and says explicitly **"Not restated here."**
> This is the document it defers to. It is a **public excerpt**: two passages are removed and marked
> below (the `run_forensics` command, and a bullet naming database paths), and it references files
> from its origin repo that are not included here — `CLAUDE.md`, `docs/INVARIANTS.md`,
> `docs/CONFIGURATION.md`, `docs/DEFERRED.md`, `.claude/hooks/`. No sentence has been rewritten. The
> four audits it tells you to run **are** included:
> [`examples/instruments/`](../../../examples/instruments/README.md).

The user has handed you a broken run and nothing else. Do **not** ask which run, do **not** ask for
logs, do **not** ask permission to start. Everything here is pre-authorized. Follow it in order.

> **First:** `CLAUDE.md` → *Before you open the first file* still applies, and applies FIRST. A run
> is evidence, not a work order. The Diagnostic Artifact is written before you open any file the run
> points at — including the module that emitted the failing verdict.

---

## 1. Gather the evidence — one command, from `src/`

> **[Command block removed for this public excerpt.]** It invoked `run_forensics`, which could not
> ship — its dependency chain terminates in application modules and it reads a database schema and a
> log format specific to the origin repo. What it produced: the run's untruncated failure text (the
> console truncates), the attempt ledger, the model/token/cost profile, external-tool activity, and
> an embedded timeline. The point that survives is the next paragraph's — **one command, before you
> open anything.**

## 2. Read the code path that failed

The pack is **measurements, not a diagnosis**. It names no cause on purpose, and its section list is
a fixed heuristic that can miss the real one entirely. Open the module that emitted the failing
verdict and confirm the mechanism yourself.

**A pack with no signal means *not measured*, never *not there*.**

## 2b. Ask what the maker was SHOWN — with the second command, not from memory

The gate that fired is where the run stopped. What the maker *received* at the moment it decided is
a different question, and reading the brief does not answer it: an omission is invisible to anyone
reading for what IS there. So run the second command over the brief that feeds the failing decision
and **paste the output**:

```bash
cd src && python tools/render_audit.py --target <module>:<function>
```

It puts the source record's columns beside what the render emits. **Referenced, not rendered** is
the bucket that has cost runs — the function held the field and printed something else.
`.claude/hooks/render_boundary_notice.py` also fires it automatically whenever you open a file that
builds model-facing text.

Run it for **every** channel-4 brief in the failing path, not just the one you suspect. Choosing
which to audit is the same judgement that produced the suspicion, so it cannot check it.

**A clean diff is not an all-clear, and the tool now says so itself.** A field can be dropped at two
earlier boundaries, and at both of them the render is faithful with nothing left to see:

```bash
cd src && python tools/projection_audit.py --source <UpstreamRecord>   # record -> record
cd src && python tools/loader_audit.py --target <module>:<function>    # record -> in-memory dict
```

The loader boundary is the least visible of the three: a schema drop at least leaves a table
definition someone can read, while a loader drop leaves only the shape of a dict literal in one
function — and every consumer inherits it silently.

All three report measurements only. Narrowing is often deliberate; the ruling is yours.

## 2c. Now check what the model ACTUALLY saw — not what the code could emit

The three audits above parse source: they show what a boundary *could* print. This one reads the
run's own record of every prompt and response and shows what was really in front of the model. Take
the literal value that is wrong and trace it:

```bash
cd src && python tools/transcript_audit.py --token <the wrong value>
cd src && python tools/transcript_audit.py --token <the wrong value> --corpus   # is it chronic?
```

**Paste the FIRST APPEARANCE line.** It decides the kind of fix before you have picked one:

| first appears in | what happened | kind |
|---|---|---|
| `📤 REQUEST` | the pipeline rendered it and handed it over — it was already wrong upstream | **(a) / (b) / (c)** |
| `📥 RESPONSE` | the model produced it — now dump the REQUEST before it (`--block N`) and read what it was given | usually still (a) |

This is the step that stops a guard being written on the consuming side just because the consumer is
where the damage became visible.

**A stub or absent story means NOT MEASURED, never "not there."** 31 of 57 archived runs recorded
zero calls because their traffic went through a seam that did not write to the story. Say so rather
than implying coverage. The tape cannot substitute — it stores a 200-char preview
(`docs/INVARIANTS.md` §2).

## 2d. Enumerate the guards already standing in this path

Before proposing anything, list the gates/guards the failing path already contains and, for each,
**what it masks**. This is the step that finds the two fix kinds nobody reaches for:

- Two guards enforcing the same rule differently → kind **(c)**, collapse them. Cross-check the
  single-source reader list in `docs/INVARIANTS.md` §1.
- A guard demanding something no maker can produce → kind **(b)**, delete the demand.

Write the list before naming a file. A guard you did not enumerate is one you are about to
duplicate.

## 2e. Paste your actual chronology

State the order you really worked in — the tool calls, as they happened — not the order that reads
well afterwards. A write-up can be reordered to look like diagnosis-then-fix; a tool-call sequence
cannot. If the guard came before the diagnosis, say so; that is the single most useful line in the
report, and it costs nothing to be honest about.

## 3. State what ended the run

The originating `[STATE]`, the failing step, the mechanism, and the concrete before/after.
Non-terminal markers (`DETERMINISTIC_FAIL`, `DEFERRED`) are context — say whether they are
load-bearing rather than assuming either way.

**`WHY RUN` stops here.**

## 4. Then fix it

Exactly as *Scope of a fix* in `CLAUDE.md` already requires: baseline suite first, branch off
`master`, ONE deadlock, maker/checker symmetry, the spec-copy sweep for the rule it touches,
after-suite with an explicit regression-vs-obsolete ruling on every new red, `docs/CONFIGURATION.md`
entry, `--no-ff` merge back to `master`, tag, no remote push, no co-author metadata.

> **`FIX RUN` is pre-authorised DIAGNOSIS and AUTHORING — never a pre-authorised git write.** The
> branch, the commit, the merge and the tag in that sentence each need the human's yes at the moment
> you reach them (`CLAUDE.md` → *ASK BEFORE EVERY GIT WRITE*). The trigger removes the questions
> about *which run* and *may I start*; it does not remove the one about moving a ref.

Anything you are not fixing is **ONE LINE** in `docs/DEFERRED.md`.

---

## Stop and ask for a ruling — before touching code — only when

- the blocking cause genuinely needs **more than one fix** (say so in two sentences), or
- the gate that fired may be **correct and the design wrong** (a defect and a working gate need
  opposite responses), or
- a **reversible flag** would settle it (config before code), or
- the fix would change **prompt bytes** in a way the user should rule on first.

Otherwise: diagnose, fix, ship, report. Do not ask *"shall I proceed?"*.

---

## Reading the evidence honestly

- **[Bullet removed for this public excerpt — it named the origin repo's live and per-run archive
  database paths. Its point: the per-run archives are the corpus for any historical sweep, and the
  only way to measure a change's real blast radius before shipping it.]**
- **There is no `sqlite3` binary in this container.** Use Python's `sqlite3` module
  (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`). A shell `sqlite3 … || echo MISSING` reports
  a false negative, because the failure is the missing binary.
- **A green offline suite says nothing about anything the tape cannot reach.** See
  `docs/INVARIANTS.md` §2 for what the evidence can and cannot prove — say "not measured" rather
  than implying coverage.
