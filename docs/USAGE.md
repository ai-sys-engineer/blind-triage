# Usage reference

More detail behind the README's quickstart: what the protocol needs you to supply, the main CLI flags,
chat-mode usage, and a note on cost. The README covers the short version; this covers the rest.
The driver's header comment, which `--help` prints, has more.

---

## What you must supply

**The protocol is *sequencing*.** It owns the order, the isolation and the stop lines, and it
deliberately does not restate what it delegates, because a second copy of a rule is a second thing to
drift. So `SKILL.md` reaches outside itself in three places, and here is what it reaches for:

| `SKILL.md` says | What it means | Included? |
|---|---|---|
| `fix-run §2b–2c` | which instrument to run at which boundary, and why | **yes** — [`.claude/skills/fix-run/SKILL.md`](../.claude/skills/fix-run/SKILL.md) |
| four tool names | the boundary audits | **yes, all four** — [`examples/instruments/`](../examples/instruments/) |
| `CLAUDE.md` | a rules file: fix kinds, the upstream question, a scope budget | **the cited part** — [`RULES_FOR_CLAUDE_MD.md`](../RULES_FOR_CLAUDE_MD.md) |

### The instruments

Four small programs, one question each. **All four are in this repo, taken from the system the
protocol was developed in** — as reference and reading material, not as utilities. They follow that
system's naming conventions and are expected to find nothing in a different codebase. What you
supply is the *equivalent* for yours; they show you what equivalent means. Full detail, including
where the coupling lives and the one adapter needed, is in
[`examples/instruments/README.md`](../examples/instruments/README.md).

| the question it settles | tool |
|---|---|
| **Did the pipeline render this, or did the model produce it?** A value first appearing in a *request* was already wrong upstream. First appearing in a *response* means dump the request before it and read what the model was given. This one decides the *kind* of fix before you have picked one, which is why it is run first. | `transcript_audit.py` |
| Diff a record against the text a function emits from it — **referenced but not rendered**, where the function had the field and printed something else | `render_audit.py` |
| Diff a record against the record it is projected into — which columns are dropped at a write boundary | `projection_audit.py` |
| Diff a record against the in-memory dict a loader builds from it — which columns never reach the consumer at all | `loader_audit.py` |

The last three are **static**: they parse Python with `ast` and execute nothing — no imports of the
audited code, no network, no database, no subprocess. They show what the code *could* emit, and **a
clean result is not an all-clear**: each one covers a single boundary, and if a column was dropped at
an earlier boundary there is nothing left to see at the next one.

The first is different in kind — it reads the run's own transcript rather than inferring from source.
It is also the only one that needs an adapter: three symbols locating your own logs.

### The rules file

`SKILL.md` defers to `CLAUDE.md` in several places and says *"Not restated here."* The part it defers
to is in [`RULES_FOR_CLAUDE_MD.md`](../RULES_FOR_CLAUDE_MD.md) — take what you want into whatever
rules file you already use. *(It is deliberately not named `CLAUDE.md`: at that name it would load
automatically and collide with yours.)* The three things it must carry:

- **The fix-kind ladder.** (a) give a consumer data it already lacks · (b) delete a demand nobody
  can satisfy · (c) collapse duplicate implementations · (d) add or tighten a check — **only** once
  a, b and c are ruled out *in writing*. Adding a check was the response reached for first here and
  the one most often wrong: it relocates a failure instead of removing it.
- **The upstream question.** What did the failing step need and not have? Does that input exist
  anywhere upstream? If it exists and is being dropped, fix *that* and stop.
- **A scope budget**, so a fix cannot quietly become a feature.

**Supply none of it and the driver still runs** — it will quarantine your report, isolate the
phases, and hold the stop lines. The evidence phase will simply have nothing to measure, and should
say so.

**None of this is reviewer work.** To see the protocol operate, read
[`examples/`](../examples/) — a real report beside the real blinded packet it produced. Nothing to
install, about a minute.

---

## Running it

**The CLI is the recommended path.** It does mechanically what the chat version asked the user to do
by hand: clear the session and hand the next phase exactly one file. Chat is documented below too —
it's the fallback, not a parallel option.

### From the terminal

`scripts/triage/blind-triage.sh` runs **one process per phase**, and that is the point rather than a
convenience: a new process *is* a cleared session — a stronger guarantee than `/clear`, which is the
step chat still requires you to remember yourself. Exactly one artifact crosses each boundary, the
packet the previous phase wrote to disk, and the original report is withheld from later phases by
where the case directory lives, outside the repo, not by asking the model not to look.

Run it with no arguments and it opens a menu:

```bash
scripts/triage/blind-triage.sh
```

Cases live under `~/.claude-triage` by default, outside the repo; `TRIAGE_HOME` overrides that.
Pointing `TRIAGE_HOME` inside the repo removes that protection.

The menu lists every case with its status and offers **one action per case**, having worked out what
that status means:

| status | what the single action does |
|---|---|
| not yet blinded | run Phase 0 — the only phase that ever sees the report |
| awaiting phase N | run Phase N with the previous phase's packet |
| phase N FAILED | resume Phase N from its salvaged transcript |
| all four done | author the fix from the plan you approved |

So you never have to remember `--phase` versus `--resume` versus `--fix`, or which of a dozen case
directories a bug lives in. `v` pages a plan before you authorise it, `b` goes back, `n` starts a new
case, `q` quits.

The flags are all still there for scripting:

```bash
scripts/triage/blind-triage.sh -f your-report.txt              # start a case from a file
scripts/triage/blind-triage.sh "ECR-114: brief drops a column" # …or from a string, or a pipe
scripts/triage/blind-triage.sh --case <dir> --phase 2          # run one phase
scripts/triage/blind-triage.sh --case <dir> --resume 3         # finish a phase that died
scripts/triage/blind-triage.sh --case <dir> --phase 4 --fix    # author, don't just plan
scripts/triage/blind-triage.sh --help
```

Four things worth knowing before you run it:

- **Phase 4 plans by default.** `--fix` is what opts into writing code, and even then the change
  lands uncommitted in your working tree. Git stays yours in every phase — the driver denies it at
  the CLI level.
- **A dead phase is recoverable.** A phase composes its packet in a single write at the very end, so
  a crash a second earlier used to cost everything it had measured. Each phase now streams its packet
  to disk *as it is typed*, alongside its narration and its reasoning trace; if it dies before writing
  anything, `extract_thoughts_v2.py` rebuilds the run from the transcript and `--resume` finishes it
  **without re-running the instruments**.
- **`--auto` removes the human pauses.** The header says it plainly: it "also removes the reason the
  protocol works." Use it knowingly.
- **It costs real money, per phase.** Each phase is its own model session, and that is the price of
  the isolation. Even a deliberately trivial run with **nothing to find** is billed for every phase it
  runs, and a real four-phase run on a real bug costs more. Budget accordingly, and use
  `--stop-after` if you only want the early phases.

**Reading the driver as a design artifact works too.** Its header comments carry most of the
reasoning: why Phase 0 was eventually given its own process, and why the case directory lives
*outside* the repo — measured, after a phase read a file it should not have been able to see, and was
denied on the identical read one directory further out.

### In a chat session

The fallback, for when you don't have or don't want a terminal — and the original way this ran,
before the CLI existed. Paste your report with `/blind-triage` in front of it — a ticket, a
spreadsheet row, a paragraph, anything works. At every stop it hands you a packet and tells you to run
`/clear` and paste that packet into a fresh session; the CLI does this same clearing for you,
automatically, between every phase. Typed bare with no bug attached, it prints a one-screen
orientation card instead of starting.

For what a report going in and a blinded packet coming out actually look like, see
[`examples/`](../examples/) — a real run, with effort made to leave the files as the run produced
them.
