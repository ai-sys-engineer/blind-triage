# A real Phase 0, start to finish

Phase 0 takes a bug report and produces a **packet**: the only thing Phase 1 (the evidence stage) is
allowed to see. The original report is then sealed. These two files are the report and the packet from
one run. Nothing to install or run; read them side by side.

| file | what it is |
|---|---|
| [`01-report.txt`](01-report.txt) | the bug report as submitted |
| [`02-phase0-packet.md`](02-phase0-packet.md) | everything Phase 1 was allowed to see |

Effort was made to leave both as the run produced them.

## The report

```
Please note, we have already made fixes to the code base recently so this bug may very well have
been impacted by the fixes post ledger of the bug. It may not even be relevant anymore, or it may
still exist.
ID: F8
Title: max_ecr_loops raised 3 -> 9 in the working tree, uncommitted
Status: Decision needed
Class: Housekeeping
Chronic?: n/a
Run / ECR: src/flow_design.py:1660 + docs/CONFIGURATION.md
Evidence: 055902 deadlocked at 3; 065833 used the raised budget and was killed at 4.
Offline testable?: n/a
```

## Four things to compare

**1 · The pointer to where the bug lives is removed.**

| report | packet |
|---|---|
| `Run / ECR: src/flow_design.py:1660 + docs/CONFIGURATION.md` | not present; listed as deleted: *"The report's SITE LIST, deleted outright: one source file with a line number, plus one documentation file path. Phase 1 is not told where to look."* |

A file path in a bug report reads like a fact. It is also the reporter's guess about where the
answer is, and Phase 1 would start there.

**2 · A claim about cause is cut, and the gap is left showing.**

| report | packet |
|---|---|
| `065833 used the raised budget and was killed at 4.` | `065833 ... was killed at 4.` |

"Used the raised budget" says the raised setting is why the run ended. That is what the investigation
is meant to find out, so the phrase is removed. The `...` marks where it was.

**3 · The title is reduced to what can be observed.**

| report | packet |
|---|---|
| `Title: max_ecr_loops raised 3 -> 9 in the working tree, uncommitted` | *"the setting `max_ecr_loops` reads 9; the value carried in committed state is 3."* |

"Raised 3 -> 9" suggests the change explains the two runs. The packet keeps the facts (current value,
committed value) and says what it dropped:

> *"The title's framing that a value 'raised 3 -> 9' is the thing that distinguishes the two runs —
> that is the report's hypothesis, compressed into something that reads like a finding."*

**4 · One judgement call is handed back to the human.**

The packet keeps the setting name `max_ecr_loops` and the numbers 3 / 9 / 4, and says so:

> `KEPT DELIBERATELY, OBJECT IF WRONG:` *the identifier `max_ecr_loops` and the numbers 3 / 9 / 4 are
> retained. The identifier is a value name the observation cannot be stated without, but it does
> point at machinery — if you want it blinded too, say so now.*

Blinding is a judgement, and judgement can be wrong. The packet lists what it deleted and stops at a
line where a human can overrule it. **Quarantine, not amnesia.**

## Other fields in the packet

- **`chosen because`** — Phase 0 must pick exactly one symptom and give a reason. Here it explains why
  the two past run endings are different events, not the same symptom, and moves them to
  `ALSO OBSERVED`.
- **`ALSO OBSERVED`** — holds what doesn't fit the chosen symptom, including the reporter's own note
  that recent changes may have overtaken the bug.
