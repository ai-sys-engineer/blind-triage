#!/usr/bin/env python3
"""transcript_audit — where a value FIRST entered the conversation, and from which side.

Why this tool exists
--------------------
The other three audits parse source: they show what a boundary *could* emit. This one reads
``logs/transparency_story.md`` — the full, untruncated prompt and response of every captured call —
and shows what the model *actually saw*. It is the fourth and last boundary, and the only one that
is evidence rather than inference.

It answers one question that nothing else here can, and that question decides the KIND of fix:

    Did this value first appear in a REQUEST, or in a RESPONSE?

* **REQUEST** — the pipeline rendered it and handed it over. Whatever is wrong with it was already
  wrong upstream. That is kind (a), (b) or (c) in ``CLAUDE.md`` → *Scope of a fix*.
* **RESPONSE** — the model produced it. Now read what the REQUEST at that moment *did* contain,
  because a model inventing something is usually a model that was shown too little.

The failure mode this exists to break is reaching for a check on the consuming side because the
consumer is where the damage became visible. A first-appearance line makes the direction of travel
a measurement instead of an intuition.

Why not the Glass Box tape
--------------------------
It cannot answer this. ``docs/INVARIANTS.md`` §2: the tape stores
``contents_preview = request["contents"][:200]`` — a 200-char stub. The story stores the whole thing.

DESIGN RULE — MEASUREMENTS, NEVER A VERDICT
-------------------------------------------
Inherited verbatim from ``run_forensics`` and the three static audits. **This tool does not
diagnose.** A token appearing in a REQUEST is not a defect; a token appearing in a RESPONSE is not a
hallucination. It reports where and when a string occurred, and stops. No "suspect", no "missing",
no severity.

Reading the output
------------------
Blocks are numbered in file order. Each carries a timestamp, a role and an agent label.

**The agent label is a GUESS and is wrong about 13% of the time.**
``transparency_logger._infer_agent`` regexes ``"You are X"`` out of the prompt, so it mislabels
whenever a *brief* happens to contain that phrase (observed: ``** SOURCE``,
``** REGULATOR (input_rail_id...)``). Never key on it. The role — REQUEST vs RESPONSE — comes from a
literal delimiter and is reliable; that is the field the conclusion rests on.

A missing or stub story means **NOT MEASURED**, never "not there". Runs whose traffic went through
an uninstrumented seam recorded nothing at all.

Usage::

    cd src && python tools/transcript_audit.py --token <the value that is wrong>
    cd src && python tools/transcript_audit.py --token <value> --run deliverables/<run>
    cd src && python tools/transcript_audit.py --token <value> --corpus
    cd src && python tools/transcript_audit.py --block <n>

Pure, offline, read-only: it streams a markdown file and never imports, executes or connects to
anything.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from run_forensics import Run, all_runs, resolve_run  # noqa: E402

#: ``### 🤖 <agent> [HH:MM:SS]`` — written by transparency_logger.log_api_call.
_HEAD = re.compile(r"^### \U0001F916 (.*?) \[(\d\d:\d\d:\d\d)\]")
#: ``#### 📤 Request`` / ``#### 📥 Response`` — the reliable field.
_REQ = "#### \U0001F4E4 Request"
_RES = "#### \U0001F4E5 Response"

#: Below this a story is a header-only stub: the logger opened the file and recorded no calls.
STUB_BYTES = 1024


@dataclass
class Block:
    """One side of one captured call.

    Attributes:
        index: Position in the file, 0-based. The stable key.
        timestamp: ``HH:MM:SS`` from the block header.
        actor: The agent label — a regex guess. Display only; see the module docstring.
        role: ``REQUEST`` or ``RESPONSE``. Parsed from a literal delimiter, reliable.
        text: The full untruncated body.
    """

    index: int
    timestamp: str
    actor: str
    role: str
    text: str


def parse(path: str) -> List[Block]:
    """Stream a transparency story into blocks.

    Streams line-by-line rather than reading whole: archived stories reach 35 MB.

    Args:
        path: Path to a ``transparency_story.md``.

    Returns:
        The blocks in file order; ``[]`` when the file is absent or unreadable. An empty list is
        "not measured", never "nothing happened".
    """
    blocks: List[Block] = []
    actor, stamp, role = "", "", ""
    buf: List[str] = []

    def flush() -> None:
        if role:
            blocks.append(Block(len(blocks), stamp, actor, role, "\n".join(buf)))

    try:
        handle = io.open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return []
    with handle:
        for line in handle:
            head = _HEAD.match(line)
            if head:
                flush()
                actor, stamp, role, buf = head.group(1).strip(), head.group(2), "", []
                continue
            if line.startswith(_REQ) or line.startswith(_RES):
                flush()
                role = "REQUEST" if line.startswith(_REQ) else "RESPONSE"
                buf = []
                continue
            buf.append(line.rstrip("\n"))
    flush()
    return blocks


def find(blocks: Sequence[Block], token: str, whole_word: bool = True) -> List[Block]:
    """Every block whose body contains ``token``.

    Args:
        blocks: Parsed blocks.
        token: The literal string to look for.
        whole_word: Bound the match on word characters, so a short numeric token does not match
            inside a longer one. Falls back to substring search when the token has no word
            characters to bound.

    Returns:
        Matching blocks in file order.
    """
    if whole_word and re.search(r"\w", token):
        pattern = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)")
        return [b for b in blocks if pattern.search(b.text)]
    return [b for b in blocks if token in b.text]


def excerpt(block: Block, token: str, context: int = 2) -> List[str]:
    """The lines around the token's first occurrence inside one block.

    Args:
        block: The block to quote from.
        token: The string to locate.
        context: Lines of context either side.

    Returns:
        Quoted lines, each truncated to keep the report readable.
    """
    lines = block.text.split("\n")
    for i, line in enumerate(lines):
        if token in line:
            lo, hi = max(0, i - context), min(len(lines), i + context + 1)
            return [f"{'>' if j == i else ' '} {lines[j][:160]}" for j in range(lo, hi)]
    return []


def story_state(run: Run) -> Tuple[str, int]:
    """Classify a run's story before trying to read it.

    Returns:
        ``(state, size_bytes)`` where state is ``ok``, ``stub`` or ``absent``. ``stub`` means the
        logger ran and recorded no calls — traffic went through a seam that does not write here.
    """
    path = run.transparency
    if not path or not os.path.exists(path):
        return "absent", 0
    size = os.path.getsize(path)
    return ("stub" if size < STUB_BYTES else "ok"), size


def _label(run: Run) -> str:
    """The run id as used for every DB key."""
    return os.path.basename(run.root.rstrip(os.sep))


def report_run(run: Run, token: str, context: int, limit: int = 5,
               whole_word: bool = True) -> List[str]:
    """Render the first-appearance report for one run.

    Args:
        run: The run to read.
        token: The literal value being traced.
        context: Lines of context around the first hit.
        limit: How many appearances to list after the first.
        whole_word: Bound the match on word characters.

    Returns:
        Report lines. Always non-empty — silence would read as an all-clear.
    """
    state, size = story_state(run)
    head = f"── {_label(run)}"
    if state == "absent":
        return [head, "   NOT MEASURED — no transparency_story.md for this run."]
    if state == "stub":
        return [head,
                f"   NOT MEASURED — story is a {size}-byte stub: the logger recorded no calls.",
                "   This says nothing about whether the run made them."]

    blocks = parse(run.transparency)
    if not blocks:
        return [head, f"   NOT MEASURED — {size} bytes present but no blocks parsed."]

    hits = find(blocks, token, whole_word)
    if not hits:
        return [head, f"   {len(blocks)} blocks parsed. '{token}' does not appear in this run."]

    first = hits[0]
    out = [head, f"   {len(blocks)} blocks parsed | '{token}' appears in {len(hits)}"]
    out.append("")
    out.append(f"   FIRST APPEARANCE   block {first.index} | {first.timestamp} | {first.role}")
    out.append(f"                      agent label (a guess): {first.actor[:60]}")
    if first.role == "REQUEST":
        out.append("                      → the pipeline rendered this and handed it to the model")
    else:
        out.append("                      → the model produced this; read the REQUEST before it")
    for line in excerpt(first, token, context):
        out.append(f"     {line}")
    out.append("")
    out.append("   then:")
    for block in hits[1:limit + 1]:
        out.append(f"     block {block.index:<5} {block.timestamp}  {block.role:<8} "
                   f"{block.actor[:44]}")
    if len(hits) > limit + 1:
        out.append(f"     … and {len(hits) - limit - 1} more")
    return out


def report_block(run: Run, index: int) -> List[str]:
    """Dump one block whole, for reading the context a first-appearance line points at."""
    state, size = story_state(run)
    if state != "ok":
        return [f"── {_label(run)}", f"   NOT MEASURED — story is {state} ({size} bytes)."]
    blocks = parse(run.transparency)
    if not 0 <= index < len(blocks):
        return [f"   block {index} out of range (0..{len(blocks) - 1})"]
    block = blocks[index]
    return [f"── {_label(run)} block {block.index} | {block.timestamp} | {block.role}",
            f"   agent label (a guess): {block.actor}", "", block.text]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Always returns 0 — a diagnostic must never fail a run."""
    parser = argparse.ArgumentParser(
        description="Where a value first entered the model's context, and from which side.")
    parser.add_argument("--token", help="the literal value to trace")
    parser.add_argument("--run", help="a run folder; default is the newest")
    parser.add_argument("--corpus", action="store_true",
                        help="every archived run instead of one")
    parser.add_argument("--block", type=int, help="dump one block whole, by index")
    parser.add_argument("--context", type=int, default=2,
                        help="lines of context around the first hit (default 2)")
    parser.add_argument("--substring", action="store_true",
                        help="match anywhere, not only on word boundaries")
    args = parser.parse_args(argv)

    if args.block is None and not args.token:
        parser.print_help()
        print("\nNothing traced. Pass --token <value> or --block <n>.")
        return 0

    runs: List[Run]
    if args.corpus:
        runs = [r for r in all_runs() if story_state(r)[0] == "ok"]
        if not runs:
            print("NOT MEASURED — no run carries a readable transparency story.")
            return 0
    else:
        one = resolve_run(args.run)
        if one is None:
            print("NOT MEASURED — could not resolve a run folder.")
            return 0
        runs = [one]

    if args.block is not None:
        print("\n".join(report_block(runs[0], args.block)))
        return 0

    print(f"transcript_audit — tracing '{args.token}' across {len(runs)} run(s)")
    print("MEASUREMENT ONLY. A value in a REQUEST is not a defect; a value in a RESPONSE is not a")
    print("hallucination. The ruling is the human's.\n")
    for run in runs:
        print("\n".join(
            report_run(run, args.token, args.context, whole_word=not args.substring)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
