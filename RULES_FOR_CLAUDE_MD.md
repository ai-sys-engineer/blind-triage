# Fix-scope rules

The lines below are the actual rule text — the part meant to go into *your* project's rules file
(`CLAUDE.md` or equivalent), not this repo's. Commands, paths and names (`transcript_audit`, `src/`,
"the maker", "vault") come from the system these rules were written in; swap in your own equivalents.

---

## Scope of a fix — ONE DEADLOCK AT A TIME

**DO NOT GO FISHING FOR OTHER UNRELATED BUGS.** Not while triaging, not while reading a file you
opened for another reason, not "while I was in there."

A run, a log, a vault, a stack trace, a screenshot, a ticket or a finding row is **evidence, not a
work order.** A pre-written diagnosis is the most binding of them, because it arrives already naming
the code to change — treat its site list as one hypothesis, not as the scope. The batch is the
user's to define. Diagnose **what ended the run**, fix that, stop.

> **SIZE BUDGET: a fix is ≤150 changed lines across ≤3 files.** Past that it is a
> *feature* — stop, describe it in three sentences, get a separate go-ahead.

### Before you open the first file

**Your first tool call should not be a read of a file the report names.**

**1. The report is a guess — the files it names AND the fix it suggests.** A report ending in
*"decide between A, B and C"* has answered step 4 for you, and picking one feels like deciding
something. It isn't. Both halves are one guess.

**2. Follow the wrong value, with the instruments — not from memory.** A stack trace shows code that
**ran**; a dropped field lives in code that **did not**, so no trace reaches it. Four boundaries,
four commands, all measurement-only:

```bash
cd src && python tools/transcript_audit.py --token <value>          # what the model ACTUALLY saw
cd src && python tools/render_audit.py --target <module>:<function> # record -> emitted text
cd src && python tools/projection_audit.py --source <Record>        # record -> record
cd src && python tools/loader_audit.py --target <module>:<function> # record -> in-memory dict
```

**Run `transcript_audit` first and paste its FIRST APPEARANCE line.** It reads the run's own record
of every prompt and response, and it decides the kind of fix before you have picked one: a value
first appearing in a **REQUEST** was rendered by the pipeline and was already wrong upstream → (a),
(b) or (c); first appearing in a **RESPONSE** was produced by the model, so dump the request before
it and read what it was given. A stub or absent story is **NOT MEASURED**, never "not there".

The other three are static: they show what the code *could* emit. **Referenced-but-not-rendered** is
the shape that has cost runs — the function held the field and printed something else. A clean
render diff is not an all-clear; a column dropped one boundary earlier leaves nothing to see there.

The only four channels model-facing text comes from: task YAML, schema field descriptions, tool
return strings, python briefs. Say which one is in front of the model **at the moment of the
decision you are grading**, not the first one you find.

**3. Look at the examples your own standards praise, before you need them.** Anything cited as *"do
it like this"* is code nobody re-reads, because being cited reads like a clean bill of health. Get
the list mechanically:

```bash
grep -ohE '`[a-z_]+\.[a-z_0-9]+`' CLAUDE.md .claude/rules/*.md | sort -u
```

**WRITE THE INTERSECTION of this list and step 2's — that is the deliverable, not the two lists.**
Beside each module put *opened* or the reason you did not. Anything in the intersection is opened
FIRST, ahead of every file the report named. A citation of **how** a module is built says nothing
about **what it emits**: the exemplar register is a suspect list, not a safe list.

**4. Say which KIND of fix you are making, before you name a file.**

| | kind of fix | the question that finds it |
|---|---|---|
| **(a)** | give a consumer data it already lacks | is the field captured upstream and dropped before it arrives? |
| **(b)** | delete a demand nobody can satisfy | is the rule wrong, rather than under-enforced? |
| **(c)** | collapse duplicate implementations | do the N copies disagree *because* there are N copies? |
| **(d)** | add or tighten a check | only once (a), (b) and (c) are ruled out in writing |

#### A new gate is not a fix

A gate is the response reached for first, and the one most often wrong: it relocates the failure
instead of removing it. **(a), (b) and (c) are the fixes.**

**Adding or widening a check is not an available fix on its own.** A gate may still ship — but as
its own `feat(gate):` commit that is not a fix and gets its own review, never smuggled in as one.

**Ruling out (a) takes the column diff, never a field lookup.** *"I looked for field X on the
consumer and it wasn't there"* tests the one field you already thought of, on one side of one
boundary. The missing field is by definition the one you were not going to think of, which is why
the diff has to do the finding rather than you.

**THE UPSTREAM QUESTION — mandatory, before any code, on every input format.** A log names the gate
that *stopped* the run; never an input dropped three steps earlier. Name (a) what the failing step
needed and did not have, (b) whether that input exists anywhere upstream, and (c) if it exists and is
being **dropped — fix that instead, and stop.** A gate compensating for a dropped input is a second
bug, not a fix. Record it as an `Upstream-checked:` trailer.

When your explanation **requires a coincidence** — a value that happens to collide, a failure that
happens to be environmental, a cause already registered as *unexplained* — that is not a finished
diagnosis. Coincidence is where the mechanism is hiding.

Measuring things to tune a new check is not a reason to have the check. *Freeze the fishing* applies
to your own proposed fix, not only to other people's bugs.

### The rest of the discipline

- **Surgical but correct.** Narrow scope is not lower quality — the one fix gets the FULL treatment:
  maker/checker symmetry, the spec-copy sweep for the rule it touches, before/after suite, the
  configuration entry. Precision is *how many things you touch*, never *how well*.
- **One deadlock per branch.** If the blocking cause genuinely needs more than one fix, say so in two
  sentences and stop for a ruling.
- **No unrequested code.** Nothing gets a branch, a file, or a test without an explicit go-ahead.
- **ASK BEFORE EVERY GIT WRITE.** Checkout, commit, merge, branch, tag, rebase, reset, stash,
  cherry-pick, add, push — **stop and ask, every time, even mid-task and even when the fix is
  finished and obviously ready.** *"Fix it"* authorises the **work**, never the **write**: it is a
  go-ahead to author a change, not to move a ref. Reading state (`status`, `log`, `diff`, `show`) is
  free.
- **A finding you are not fixing is ONE LINE** in a deferred register. No investigation, no causal
  chain, no snippets, no severity ranking. Noticing is cheap; the writeup is what costs.
- **"I also found N other things" is not a deliverable.** Do not lead with it, offer to fix it, plan
  it, or save it to memory.
- **Config before code.** If a reversible flag would settle it, propose the flag first.

**Freeze the fishing.** No proactive defect or gate hunting · no cross-copy spec sweeps beyond the
rule the one fix touches · no corpus measurements unless asked.

**The user's words override this section**, per message:

| they say | you do |
|---|---|
| *"what ended it?"* | diagnosis only — no fix proposed |
| *"fix it"* | one fix, authored and explained — **ask before the branch, and again before the commit** |
| *"register only"* | append lines to the deferred register, nothing else |
| *"open season on X"* | hunt in X — because they chose it |
| *"FIX RUN"* | the standing protocol — no path needed, no questions first |
| *"WHY RUN"* | same, but stop at the diagnosis — no fix proposed |
