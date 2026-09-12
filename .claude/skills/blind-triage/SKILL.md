---
name: blind-triage
description: Phased, context-cleared triage for a bug that arrives ALREADY DIAGNOSED — a findings row, an ECR/defect ID, a ticket, a spreadsheet cell, a screenshot, a pasted analysis, or any report whose title names a mechanism rather than a symptom. Use whenever the input tells you what KIND of bug it is before you have opened a file. Typed bare with no bug attached, it prints the orientation card. Quarantines the report's framing, splits the work into phases separated by a context clear, and tells the human exactly what to do and what to watch for at each boundary.
---

# `blind-triage` — the report is a suspect, not a witness

Fires on the input class that **bypasses `fix-run`**: a defect that arrives pre-diagnosed.
`fix-run` triggers on "FIX RUN" / a broken run; a findings row never says those words, so its
warnings never load. That routing gap is measured — see *Why* below.

> **Sequencing only.** Instruments, fix kinds, the size budget and the upstream question live in
> `CLAUDE.md` → *Before you open the first file* and `fix-run` §2b–2c. **Not restated here**
> (`docs/INVARIANTS.md` §1 — a second copy is a second thing to drift). This file governs
> **order, blinding, stop lines, and what the human is told to watch for.**

---

## 0. BARE INVOCATION — no bug attached

If the user typed `blind-triage` (or `/blind-triage`) with **no defect, report or run attached**,
they are asking for the briefing. **Print the card below verbatim, then stop.** Do not start a
phase, do not ask which bug, do not summarise it differently each time — the point is that it reads
identically every time so it can be skimmed in five seconds.

```
blind-triage — ORIENTATION

WHAT IT IS
• Phased triage for bugs that arrive ALREADY DIAGNOSED — findings row, ECR ID, ticket,
  screenshot, pasted analysis. Anything whose title names a mechanism, not a symptom.
• Fires automatically on that input class. No trigger word needed.
  Typing `blind-triage` forces it — or prints this card when no bug is attached.
• Sequencing ONLY. Instruments, fix kinds and the size budget stay in CLAUDE.md +
  fix-run §2b-2c. What this adds is the thing prose couldn't: STOP LINES.

YOUR TWO JOBS  (I will prompt you for both — you don't have to remember them)
• At each STOP    → run /clear, then paste the block I hand you.
                    Clearing is the one move only you can make.
• Before any fix  → ask me: "What single result would have proved this wrong,
                    and did you run it?"

THE GLANCE CHECK  (needs no expertise)
• A handoff packet must contain NO THESIS — commands, output, open questions only.
• If you can read a sentence saying what the bug IS → contaminated. Bounce it.
• Every packet carries an ORPHAN OBSERVATIONS field. Missing, or blank without the
  literal word NONE → bounce it. That field is where the answer hid last time.
• A DEFERRED line for something on the FAILING PATH = a fix that moved, not a fix that
  shipped. Bounce it and ask which drop was further upstream.
• A ledger with `unproven` or `ASSERTED` rows ABOVE the one being fixed = an unfinished
  ranking. Bounce it. "Costs money" / "model-behaviour question" is a question owed to
  you, not a verdict.
• [one bullet removed for this public excerpt — run recordings, separate repo]

★ THE SINGLE OBSERVABLE — watch for this above all else
• Did I name a cause during PHASE 1?
• Counts as a violation: a suspect module, an "intersection", a fix kind, a
  "this looks like…" — hedged, parenthetical or in passing all still count.
• Precedent: a session named the culprit in the SAME MESSAGE as its first tool result.
• If you see it: the protocol has collapsed and everything after it is theatre.
  Say `blind-triage` and make me restart from Phase 0.

THE PHASES
• 0  Quarantine    I restate the report as ONE symptom, show you what I deleted, and
                   show you what I set aside as NOT the symptom — object here, it's cheap
• 1  Evidence      Instruments run. NAMING A CAUSE IS FORBIDDEN.      → STOP + /clear
• 2  Accounts      2-3 rival explanations + the test that kills each  → STOP + /clear
• 3  Discriminate  Run those tests. Survivors only — UNLESS none do.  → STOP + /clear
• 4  Fix           Drop ledger first: most upstream drop wins. CLAUDE.md rules from here

HONEST LIMITS
• Phase 0 blinding happens after I've read the title, so I can under-blind. That's why
  the packet lists what I deleted — so you can object. Quarantine, not amnesia.
• Re-pasting the original report at any later phase re-poisons it. Once blinded, sealed.
• Buys sequencing, not insight. It stops me collapsing evidence and hypothesis into one
  breath. It does not make me smarter about your pipeline.
• Every stop line can hold and the answer still be missed — that has happened.
  The phases police the ORDER of my thinking; only the orphan field catches what my
  thinking never had a slot for.
```

---

## Why this exists (measured)

A findings row whose title named a mechanism was handed over with the correct rules loaded, four
purpose-built audit tools available, and a hook designed to catch its shape.

The session ran the right commands, **pasted output that contained the answer**, read past it, and
spent the rest of the session validating the mechanism the title had named. Its proposed fix was
inoperable against the real data. Its corpus validation was hand-built instead of taken from the
code path, so it confirmed the hypothesis by construction and reported a perfect score.

Four earlier sessions failed the same way. **Prose has now lost five times.** The failure is not
ignorance — it is attention: the title decides where you look before you know you are looking. So
this skill never asks you to notice anything. It asks you to **stop at a line.**

### The sixth loss happened INSIDE this skill

Every stop line held. No cause was named in Phase 1, Phase 2 produced three unranked rivals, Phase 3
built every fixture by calling the production loader and killed all three on their own stated
conditions. The report was accurate, well-evidenced — and did not contain the answer.

Two mechanisms, and both are now carried by a field rather than by advice:

* **The report shape decided what could be seen.** With the deliverable defined as "three tests,
  three verdicts, nothing else", every observation was sorted by *does this bear on A, B or C?* The
  evidence that mattered — the verbatim brief the maker was reading when it wrote the wrong value —
  bore on none of them, had nowhere in the template to go, and was dropped. Dropping it **felt like
  discipline**, which is why no amount of warning reaches it. → *ORPHAN OBSERVATIONS*, below.
* **A named hole read as a discharged one.** The session was told three of the four model-facing
  channels were unmeasured, wrote that down as a known limitation, and never ran the twenty-second
  command that measures the fourth. The cause was in that channel. → *zero survivors is not a
  finished phase*, below.

### The seventh — the forms bound, and an instrument was missing

Different from the first six: **nothing was ignored.** Every stop line held again, the orphan field
again carried the unexplained observations forward, and the Phase 4 plan was internally consistent.
What went wrong was upstream of attention, in the shape of the forms themselves. Three carriers, all
added above; none of them is advice, and none of them asks anyone to notice anything.

* **A compound `observed:` has no legal answer in the Phase 4 column.** The report offered its
  subject plus a corroborating *"also seen in run B"*. Both were observable, so both were kept — the
  Phase 0 filter ranked nothing — and the ledger's binary column then could not score a row bearing
  on one of them. Sub-symptoms were invented to make it scoreable. → *`observed:` carries ONE
  symptom*, Phase 0.
* **`unproven` was a terminal state with no owed action.** *"Prove it or strike the line"* offers
  two exits and forbids no third, so unresolved rows sitting **above** the chosen one were ranked
  past, in a ledger whose ordering principle is *most upstream wins*. The adjacent
  asserted-cost rule was scoped to the chosen fix and did not reach them. → *`unproven` is a hole in
  the ranking*, Phase 4.
* **[Third bullet removed for this public excerpt]** — it concerned a separate repo's
  run-recording machinery. It is why the paragraph above says *three* carriers.

**What this entry does not say** is which diagnosis was right. That is not the point and was never
established here; the protocol's job is to make the honest output reachable, and on this input two
of its forms made a stop-and-ask unreachable while a third instrument sat unlisted.

---

## Phase 0 — Quarantine the report (FIRST output, before any tool call)

Do not open a file. Do not run a command. Restate the report as **what was observed, only** — then
pick which single observation is the symptom.

- **Keep:** values, identifiers, file/run names, counts, what a human could see happen.
- **Delete:** any noun phrase naming a mechanism, cause, code site or fix. Titles are the worst
  offenders — they compress a guess into something that reads like a finding.
- **Delete the report's site list.** It is one hypothesis, and the one most likely to be adopted
  without noticing.

### `observed:` carries ONE symptom. Everything else observable goes below it.

A report offers several true observations — the event it is about, plus corroboration ("*also seen
in run B*"), plus context. **Keeping is not ranking, and the keep/delete filter above does not
rank.** Weld two into `observed:` and the damage lands two phases later, mechanically: Phase 2
requires accounts explaining *"the whole symptom"*, so every account stretches to cover a
conjunction; and **Phase 4's ledger column is binary**, so a row bearing on one half of a compound
symptom **has no legal answer**. The only way to answer an unanswerable column is to invent
sub-symptoms and score half-credit — which is how a fix lands on the half nobody reported.

So **pick one**, and say in one line why. Everything else observable goes to `ALSO OBSERVED`,
carried forward verbatim — visible, objectable, and **out of scope for the Phase 4 ledger**. Not
deleted, not judged less important; simply not what this triage is answering. That one line is the
cheapest correction point in the protocol: the user fixes it here in five seconds, or lives with it
for four phases.

**One symptom is not one run.** The test is *"is this the same event?"*, never *"is this the same
run?"* — so **N runs showing the same event are ONE symptom** and all N stay in `observed:`, which
is what makes a chronic finding tractable and its recurrence part of the evidence. What goes to
`ALSO OBSERVED` is a **different** event that happens to be described nearby: another failure mode,
another quantity, another gate, offered as corroboration or colour. If you cannot tell which you are
holding, the question that decides it is *"could one fix address both, or would each need its own?"*
Two events needing two fixes are two symptoms, however adjacent they looked in the report.

Emit, and **lead with the watch-for banner** so the user is armed before Phase 1 runs:

```
═══ blind-triage ENGAGED — Phase 0 of 4 ═══
★ WATCH ME IN PHASE 1: if I name a cause — a suspect module, an "intersection", a fix
  kind, even hedged — the protocol has collapsed. Say `blind-triage` to restart.
  (Type `blind-triage` any time for the full card.)
★ CHECK THE FIRST LINE BELOW: `observed` must name ONE symptom. If I picked the wrong
  one, or split one event into two, say so NOW — it is a five-second fix here and a
  four-phase problem later.

BLINDED SYMPTOM (carried forward; the original report is now SEALED)
  observed : <ONE symptom — values, identifiers, what happened>
  chosen because : <one line: why this one and not the others>
  runs     : <ids>
  ALSO OBSERVED (not the symptom; carried forward, NOT scored by the Phase 4 ledger):
    <every other observable thing the report stated, verbatim, one per line>
  NOT carried forward: <the mechanism words deleted — listed so the user can object>
```

**The blinded symptom — never the original report — heads every later packet.** If the user
disagrees with the blinding, or with which symptom was chosen, they fix it here, once.

> **Headless (`scripts/triage/blind-triage.sh`) runs Phase 0 as its OWN process.** In chat, 0 and 1
> share a context and that is correct — a human is present to object between them. Headless nobody
> is, and sharing meant the raw report sat in front of Phase 1 for the whole evidence phase, making
> this the one boundary enforced by self-restraint rather than by machinery. There, Phase 0 writes
> `packets/phase0.md` and Phase 1 inherits that and nothing else. Two consequences worth knowing
> when you read a headless packet: the *"object here, it's cheap"* stop is a real stop, and
> **`NOT carried forward` is shown to the human but withheld from Phase 1** — its content is the
> deleted mechanism words, so carrying it would undo the blinding through the field that proves the
> blinding happened.

---

## Phase 1 — Evidence. Naming a cause is FORBIDDEN.

Run the instruments (`CLAUDE.md` step 2; `fix-run` §2b–2c for which and why). Then stop.

**Hard ban, and it is the whole trick:** you may not write a sentence proposing a cause, a suspect
module, an "intersection", or a fix kind. Not as a hunch, not as a hedge, not parenthetically. The
precedent session declared its cause **in the same message** as its first tool result — there was
never a moment where evidence existed without a thesis attached to it.

Two rules that the precedent failure turned on:

- **Audit every boundary in the failing path, not the one you suspect.** Choosing which to audit is
  the same judgement that produced the suspicion, so it cannot check it (`fix-run` §2b).
- **A tool that returns a list is where the search dies.** Give **every** row a one-word verdict in
  writing. The precedent: an audit returned a list of dropped columns, the session took the one that
  suited the hypothesis it was already forming and never mentioned the rest. N rows, N verdicts — a
  blank is visible, an omission is not.
- **An escalation is a command, not a caveat.** When a tool reports that its own output is not an
  all-clear and names the next one to run — run it in THIS phase and paste its output. A
  named-but-unrun escalation is the same hole as an unmeasured channel, and the boundary it points
  at is upstream of the one you are standing on, which is the direction the answer has been in.
- **Anything you set aside gets written down VERBATIM, in the orphan field.** The same trick as the
  line above, one level up: a measurement belonging to no hypothesis has nowhere to go in a report
  organised by hypotheses, so it evaporates — and it evaporates *while you feel disciplined for
  staying narrow*. If you caught yourself thinking "interesting, but not what I'm testing", that is
  the exact sentence that precedes the loss, and the observation goes in the packet untouched. `NONE`
  is a claim you are making, not a default.

> **[Section removed for this public excerpt — it was specific to a separate repo's
> run-recording machinery. See README § *What you must supply*.]**


**STOP.** Emit:

````
═══ PHASE 1 COMPLETE — EVIDENCE ONLY (1 of 4 done) ═══
YOUR MOVE: run /clear, then paste the block below into the fresh session.

★ WATCH FOR IN PHASE 2: it must give you 2-3 RIVAL accounts and refuse to rank them.
  If it recommends one, or one arrives sounding obviously right — bounce it and say
  "give me the second account". A favourite in Phase 2 is the old failure returning.

<paste-ready block>
  blind-triage PHASE 2. You have no prior context. Do not seek the original report.

  BLINDED SYMPTOM: <from phase 0, INCLUDING its `ALSO OBSERVED` field — carried
  verbatim, still flagged as NOT the symptom and NOT scored by the ledger>

  COMMANDS RUN + VERBATIM OUTPUT:
  <literal output, untruncated, every command>

  EVERY-ROW DISPOSITION:
  <each row of every list the tools returned, with its one-word verdict>

  BOUNDARY DROPS (every field or value an audit reported as not crossing a boundary, each
  with the boundary it died at; upstream-first; no thesis, no ranking, no fix implied):
  <one line each>

  ORPHAN OBSERVATIONS (verbatim; no thesis attached; NONE is a claim, not a default):
  <every measurement you looked at and set aside because it fit no hypothesis —
   pasted as the tool printed it, not summarised>

  OPEN QUESTIONS (no answers):
  <questions the output raised>

  YOUR TASK: produce 2-3 COMPETING accounts of this evidence and the single
  discriminating test for each. Do not pick a favourite. Do not open a file any
  account names until the discriminating tests are written.
</paste-ready block>
````

---

## Phase 2 — Competing accounts (fresh context)

From the packet only. Produce **2–3 rival accounts** that each explain the whole symptom, and for
each the **single test that would kill it**.

- At least one account must be *"a consumer is being starved of a field that exists upstream"* — the
  shape that has cost this repo the most runs, and the one a mechanism-titled report hides best.
- Ranking is forbidden. If one looks obviously right, you have not found the second one yet.
- **An account that needs an "and" is a Phase 0 bug, not a bigger account.** If covering the
  `observed:` field requires a conjunction — *this account explains the loop **and** the unrelated
  thing in the other run* — the symptom was compound and Phase 0 under-ranked it. **Bounce to
  Phase 0; do not stretch the account.** A stretched account is untestable in one shot, which means
  its Phase 3 test will be a proxy, which means its death proves nothing. Three stretched accounts
  dying together reads as triangulation and is a shared blind spot with one cause upstream.
- **A test that would confirm an account does not count.** Models reliably propose confirming tests;
  the discriminating test is the deliverable.
- **A ruled-out account seals the CLAIM it names, never the channel it arrived on.** *"The model
  didn't hallucinate — its answer was correct for the part it was asked about"* closes one claim and
  leaves the live one wide open: *was it shown enough to answer any differently?* Carrying a dead
  account forward as a sealed **area** is how an entire boundary goes unexamined by three accounts at
  once.
- **Orphans are carried forward, not consumed.** Every orphan observation from Phase 1 reappears in
  this packet verbatim, each with one line naming which account claims it — or `claimed by none`. An
  orphan no account explains is the most valuable line in the packet; it is what a fourth account
  would be built from.

**STOP.** Same packet shape — accounts + tests, **no recommendation**, orphans **and `BOUNDARY
DROPS`** carried verbatim — plus:

```
═══ PHASE 2 COMPLETE — RIVAL ACCOUNTS (2 of 4 done) ═══
YOUR MOVE: run /clear, then paste the block below.

★ WATCH FOR IN PHASE 3: every fixture must be built by CALLING THE REAL CODE.
  If you see sqlite3, a SQL string, a vault dump or a hand-written dict standing in
  for real data — bounce it. That is exactly how a past "fully validated" fix turned
  out inoperable: it tested imagined data, not what the function receives.
  ALSO: each test must say whether it tests the account's CLAIM or a near-neighbour
  PROXY. A proxy test does not kill. If everything died, ask which kind killed it.
```

---

## Phase 3 — Discriminate (fresh context)

Run the tests. Report which accounts died and which survived. Nothing else.

**Build every fixture from the production path.** Call the real loader, the real function. A fixture
hand-built from SQL, a vault dump or a JSON literal tests the data you *imagined*, not the data the
code receives.

If two accounts survive, say so and stop. Do not break the tie by preference.

### Check each kill condition BEFORE you run it

Phase 2 wrote the kill conditions; Phase 4 will act on their verdicts; **you are the only phase that
sees both the condition and the data**, so a malformed one dies here or never. One line per test,
before running it:

> **Does this test's object match the account's CLAIM, or a proxy for it?**

The failure shape is specific and it looks like rigor: an account claims *no X exists*, and the test
asks *is Y present?* where Y is a near neighbour of X. Y is measurable and X is awkward, so the test
gets written against Y, run faithfully, and reported as a kill. **A test of a proxy does not kill.**
Say so, name the mismatch, and either write the test the claim actually needs or return the account
alive with the condition marked unworkable.

This also changes what a total wipeout means. When every account dies, say **whether they died on
their claims or on their wording** — *zero survivors from proxy tests is not zero survivors*, and it
bounces the Phase 2 packet rather than burying the accounts under it.

### If ZERO accounts survive, the phase is NOT over — and "nothing else" lifts

Killing everything is the one outcome that proves the accounts were never the answer, so continuing
to report only their corpses is a formality. The exit condition becomes: **close the holes this
packet names.**

> **A limitation you can write down is a command you owe.** Run it, or write one line saying why you
> chose not to. Naming a gap costs nothing and reads as rigor — which is precisely why it must never
> count as discharging one. "Known hole: channel X is unmeasured" in a report you are ending is a
> to-do you have converted into a disclaimer.

Then: **which instrument you ran was chosen by the accounts, and the accounts are now all dead.**
Re-read the failing path's boundaries with none of them in mind (`CLAUDE.md` step 2 lists the four,
`fix-run` §2b says which and why) — starting with any boundary no account ever sent you to. Three
accounts agreeing on where to look is not triangulation; it is a shared blind spot, and their
unanimous death is the evidence for that.

One ordering rule, because it is what the last loss turned on: **a first-appearance line names who
introduced the STRING, not who made the DECISION.** When the wrong value was authored by a model,
the artifact you owe is the verbatim text in front of that model *at the moment of the decision you
are grading* — the same phrasing, and the same four channels, as `.claude/rules/gate-symmetry.md`.
Mechanics live there and in `CLAUDE.md`; this file only fixes when it happens, which is **before**
Phase 4 is allowed to start.

**STOP.** Packet: surviving account(s) + the evidence that killed the others + the orphan field
(carried forward, plus anything the tests turned up that no account claimed) + `BOUNDARY DROPS`
carried verbatim, plus anything these tests added to it — Phase 4 is cold and cannot rebuild that
list, plus:

```
═══ PHASE 3 COMPLETE — SURVIVORS (3 of 4 done) ═══
YOUR MOVE: run /clear, then paste the block below.

★ IF I REPORTED ZERO SURVIVORS: there is no fix to carry into Phase 4, and the phase is
  not finished. Ask me two things before you accept it:
    "Which holes did you name, and did you run them?"   (naming one is not closing it)
    "Which boundary did none of the three accounts send you to, and did you look?"

★ YOUR KILLING QUESTION IS DUE IN PHASE 4. I should answer it unprompted:
  "What single result would have proved this wrong, and did you run it?"
  If I present a fix without answering it, ask — and don't accept "I verified it".

★ ALSO DUE IN PHASE 4: "What drops did you find on this path, and is the one you fixed
  the furthest upstream?" If the answer names a DEFERRED line, that is the miss.
  And: "Is any row ABOVE the one you fixed still `unproven` or `ASSERTED`?" If yes, the
  ranking is unfinished — the honest output is a question to you, not a plan.
```

---

## Phase 4 — Fix (fresh context)

Only now does a fix exist. Everything from here is `CLAUDE.md`: one deadlock, the size budget, the
fix kinds, maker/checker symmetry, the trailers, the testing protocol.

### If Phase 3 handed you MORE THAN ONE survivor, classify EACH before opening a file

Phase 3 is allowed to end with two live accounts ("If two accounts survive, say so and stop. Do not
break the tie by preference."). Phase 4 is where that tie actually gets broken, and **picking
whichever survivor is easiest to test is not breaking it on the merits — it is breaking it on your
own convenience**, and CLAUDE.md already has the rule that should decide it instead.

One run is why this is here. Two accounts survived: one a downstream join-scoping
claim with a clean, runnable pure-function test; the other an upstream claim whose OWN evidence,
already sitting in the Phase 3 packet, stated the bad value's first appearance was in a **REQUEST**
at a named transcript block. CLAUDE.md's own routing rule — *"a value first appearing in a REQUEST
was rendered by the pipeline and was already wrong upstream → (a), (b) or (c)"* — was never applied.
The upstream account got a paragraph of reasoning for why it probably didn't matter; the downstream
account got `render_audit`/a real test; the fix shipped against the wrong layer.

**Mandatory, before any file is opened to write code:** for EVERY surviving account, write one line —
`<account> — first appearance: REQUEST | RESPONSE | not established`. If Phase 3's packet already
names a REQUEST appearance for an account (it will have, if that account's evidence came from
`transcript_audit`), that classification is not yours to re-litigate in prose — it is CLAUDE.md's own
signal that the account routes to (a)/(b)/(c) upstream, and `render_audit` / `projection_audit`
against the module that built that request must actually run before you set the account aside. A
sentence explaining why you find the other account more compelling is not that instrument and does
not discharge it.

Only once every survivor carries a REQUEST/RESPONSE line — and any REQUEST-classified survivor has
actually been run through the audits, not reasoned about — may you pick which one to fix.

### If the instruments found MORE THAN ONE DROP, the fix goes to the most upstream one

Picking the account is not picking the SITE. A failing path usually leaks in more than one place,
and Phase 4's next temptation is not the wrong boundary — it is the RIGHT boundary and the wrong
site on it: fix the drop nearest the symptom, file the one behind it as a deferred line. That reads
as scope discipline. It is also the one move that cannot be undone later, because shipping the near
fix **retires the symptom**, and a deferred line with no live symptom is never picked up again.

**One sentence before you build it: can the instruments see this path's shape?** The four audits
answer one question — *did a field fail to cross a record boundary?* If the deciding boundary has no
record→record or record→dict projection for them to diff — a sequencing, ordering or
duplicate-implementation shape — **say so in one line, and mark which ledger rows are hand-built
rather than instrument-built.** A hand-built row may still win. It may not inherit authority it did
not earn by sitting in a table of measured ones.

**Mandatory, before any file is opened to write code — the DROP LEDGER.** One line per drop in the
packet's `BOUNDARY DROPS` field, ordered upstream → downstream:

    <boundary> · <field or value that did not cross> · would fixing THIS ALONE have
    prevented the symptom?  yes | no | unproven · <the command that produced this
    verdict, or the word ASSERTED>

**"The symptom" is the Phase 0 `observed:` field, verbatim.** You may not introduce sub-symptoms to
make a row scoreable, and the packet's `ALSO OBSERVED` entries are not scored at all. A row that
would have prevented *part* of the symptom is a `no`. If `observed:` looks compound from here, that
is a Phase 0 defect — say so and stop; it is not yours to resolve by splitting it.

How it is read — this is the ranking, not an input to your judgement:

- **The fix goes to the topmost `yes`.** Not the cheapest, not the one already open in your editor,
  not the one whose test you can already picture.
- **`no` on the near drop is a verdict, not a footnote.** A drop that would not alone have prevented
  the symptom is not the fix; it is an improvement you happened to find while looking.
- **`unproven` is a hole in the ranking, not an abstention.** You cannot know a `yes` is *topmost*
  while an unresolved row sits above it — in a ledger whose whole ordering principle is *most
  upstream wins*. Every `unproven` row **upstream of the row you intend to fix** is resolved to
  `yes` or `no` before you may fix anything below it. **Prove it, strike it, or stop and ask —
  three options.** *"It would cost money"*, *"it is a model-behaviour question"*, *"it needs its own
  ruling"* **are the stop-and-ask.** They are not a fourth option that lets the ranking continue
  past them.
- **A verdict reasoned from a module's name or docstring is `ASSERTED`, and it is not a
  measurement.** Phase 1 requires N rows, N verdicts, because *a blank is visible and an omission is
  not* — but a **cheap** verdict is invisible in exactly the way a blank is not, and one word of
  plausible reasoning retires a row as effectively as a command does. **A ledger may not be ranked
  while any row upstream of the intended winner is `ASSERTED`.** Scoped deliberately: it binds the
  handful of rows above your candidate, never all of them.
- **Two `yes` rows are not a licence to choose.** That is the multi-survivor case again — say so in
  two sentences and stop for a ruling.

**No `BOUNDARY DROPS` field in the packet is a Phase 1 OMISSION, never an empty ledger.** A packet
predating this section, or a Phase 1 that skipped the field, leaves you with nothing to rank — and a
rule that quietly no-ops when its input is missing is the "reads as rigor, does nothing" failure this
skill keeps losing to. **Rebuild the field yourself before writing the ledger:** re-run the
boundary audits across the failing path, follow every escalation they name, and paste what they
print. You may not proceed to a fix on the grounds that no drops were listed. An empty ledger is a
claim that the path has no drops, and it needs the same measurement behind it as any other claim.

**An audit that escalates has not finished.** When an instrument reports that its own result is not
an all-clear and names the next command, that command's output **outranks** the one that sent you
there. Running the escalation and then fixing the nearer drop anyway is the exact shape this section
exists to stop — the measurement was taken, then overruled by the convenience of the site already
open.

**"Too big" is a STOP, never a substitution.** If the topmost `yes` looks past the size budget:
measure it first — an *asserted* cost used to justify deferring is not a measurement, and has been
wrong here — and if it genuinely exceeds, describe it in three sentences and stop for a go-ahead
(`CLAUDE.md` → *Scope of a fix*). Shipping the downstream fix instead is not a smaller version of
that decision. It is a different fix, and it spends the symptom that would have justified the real
one.

**That rule covers cost used ANYWHERE in the ledger, not just on the row you chose.** An asserted
price — API calls, engineering time, "this needs its own ruling" — is not a measurement whether it
defers *the fix* or leaves *an upstream row unproven*. The second form is the dangerous one, because
it never looks like a deferral: the row keeps its `unproven`, the ranking walks past it, and the
plan reads as if the cheaper row won on the merits.

**`DEFERRED.md` does not accept a drop on the failing path.** The register is for findings you were
not looking for. A drop the instruments handed you *while tracing this symptom* is inside the batch,
and a one-line entry for it is Phase 3's disclaimer trick moved one phase later: *naming a gap costs
nothing and reads as rigor, which is precisely why it must never count as discharging one.*

**One alarm specific to this class:** if you find yourself arguing that your new check counts as
`Fix-kind: a` — **stop.** That argument *is* the diagnosis. `fix_scope_guard.py` refuses `d` because
a gate relocates the failure; reasoning around the refusal is how a past session shipped a guard
mislabelled as an (a).

Answer the killing question **unprompted** before presenting anything.

---

## If the phases are collapsed

If you notice you have skipped ahead — you named a cause in Phase 1, or you are reading a file the
report named before the discriminating tests exist — **say so plainly and restart from Phase 0.**
Tell the user which phase was violated and how, in one line. A collapsed protocol produces a
confident, well-formatted, corpus-validated wrong answer, which is strictly worse than an obviously
incomplete one, because it survives review.
