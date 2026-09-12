# Instruments: reference copies

These are tied to the codebase they came from; they are meant to be read.

They are the four boundary audits the protocol refers to, from the system it was developed in. Effort
was made to keep them as they were, so that the references in `SKILL.md` point at something concrete
instead of at a name. They follow that system's conventions: in another repository, three run and are
expected to report no findings, and the fourth needs a small adapter to import (documented below).

The protocol is portable; the probes are specific to a codebase. These show what an equivalent looks
like.

The three source audits parse Python with `ast` and do not import or execute the code under audit.
`transcript_audit` reads a text transcript. None of the four makes network or subprocess calls itself.

---

## What each one answers

| tool | the question it settles | boundary |
|---|---|---|
| [`transcript_audit.py`](transcript_audit.py) | Did the pipeline render this, or did the model produce it? | what the model was shown |
| [`render_audit.py`](render_audit.py) | Did the function hold this field and print something else? | record → emitted text |
| [`projection_audit.py`](projection_audit.py) | Which columns have nowhere to land in the derived record? | record → record |
| [`loader_audit.py`](loader_audit.py) | Which columns never reach the consumer at all? | record → in-memory dict |

`transcript_audit` is listed first. It differs from the other three: they parse source and show what a
boundary could emit, while it reads the run's own record of every prompt and reply and shows what was in
front of the model. Where a value first appears:

- in a **REQUEST** — the pipeline rendered it and handed it over, so the value was already present
  upstream.
- in a **RESPONSE** — the model produced it, and the request before it is the next thing to read.

It does not import as it stands; see *The one adapter*, below.

`loader_audit` covers the record-to-dict boundary. A schema change leaves a table definition to read; a
loader leaves only the shape of a dict literal in one function, and every consumer of that function
receives the same dict.

All three source audits print measurements and do not rule on them. Narrowing is often deliberate — a
demand table *should* be demand-shaped. They show which columns do not make the trip, not whether they
should have.

A clean result covers one boundary. If a column was dropped at an earlier boundary, there is nothing to
see downstream. When `render_audit` detects that shape it prints `NOT AN ALL-CLEAR` and names the
upstream record to check next.

## Where the coupling lives

These constants tie the tools to the original codebase and are the adaptation surface:

```python
render_audit.py:365   RECORD_MODULE   = "db_models.py"          # a literal filename
render_audit.py:70    _NAME_PREFIXES  = ("format_", "compose_") # how it finds text builders
render_audit.py:71    _NAME_CONTAINS  = ("brief",)
render_audit.py:75    _HOUSEKEEPING   = {"id", "project_id", "iteration_idx", ...}
loader_audit.py:72    _LOADER_HINTS   = ("load", "fetch", "read_", "_rows", "select")
```

The scan glob is inline rather than a constant, at `render_audit.py:504` and `:619`.

Each tool resolves its scan root as `Path(__file__).parent.parent`, so it expects to live at
`<scan-root>/tools/`; here it sits in `examples/instruments/`.

## The one adapter — `transcript_audit` does not import as it stands

Running it here raises `ModuleNotFoundError: No module named 'run_forensics'`:

```python
from run_forensics import Run, all_runs, resolve_run   # transcript_audit.py:73
```

`run_forensics` is a module that reads a SQLite store and imports application modules; it is not
included. `transcript_audit` uses only three symbols from it, and they form a locator — everything else
in the file is stdlib:

```python
@dataclass
class Run:
    root: str            # the run folder — used for the display label
    transparency: str    # path to the transcript file — the only field that matters
    # run_forensics' Run also carries terminal_log / api_audit / vault; this tool reads neither

def resolve_run(path: str | None = None) -> Run | None   # one run; newest when path is None
def all_runs() -> list[Run]                              # the archive, for --corpus
```

Pointing these at another location for prompt/response logs is the adapter.

The transcript *format* is not covered by it. `parse()` keys on the original logger's literal
delimiters — `### 🤖 <agent> [HH:MM:SS]`, `#### 📤 Request`, `#### 📥 Response`. Other logs will have
different ones. The structure `parse()` produces, `Block(index, timestamp, actor, role, text)`, does not
depend on them.

Two details if you rebuild it:

- **The agent label is inferred from the prompt text and can be wrong.** It is regexed out of the
  prompt, so it mislabels when a brief happens to contain `"You are X"`. The **role** — REQUEST vs
  RESPONSE — comes from a literal delimiter, so the conclusion rests on the role.
- **A missing or stub transcript is reported as `NOT MEASURED`, not as absence.** Runs whose traffic
  went through an uninstrumented seam recorded nothing, and the tool says so in those words instead of
  returning an empty result.

## The map: `fix-run`

Which instrument to run at which boundary, and why, is in
[`.claude/skills/fix-run/SKILL.md`](../../.claude/skills/fix-run/SKILL.md) — §2b and §2c.
`blind-triage/SKILL.md` cites that document and refers to it instead of repeating its rules.
