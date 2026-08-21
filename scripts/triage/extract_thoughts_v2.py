#!/usr/bin/env python3
"""Rebuild a whole run — thoughts, tool calls, tool output — in sequence, for feeding back.

WHAT THIS IS FOR
----------------
`extract_thoughts.py` recovers the reasoning. That is not enough to *resume* a dead phase: the
reasoning refers constantly to things the model saw, and without them it reads like one half of
a phone call. This produces the other half — the full run, in the order it happened:

    THOUGHT      -> what it was reasoning
    TOOL CALL    -> what it ran
    TOOL RESULT  -> what came back
    ASSISTANT    -> what it said out loud

The output is designed to be pasted into a fresh session as context, so the resumed phase
inherits the run instead of re-deriving it. Everything is verbatim and in transcript order;
nothing is summarised or reordered.

DEDUPLICATION (the same hazard as v1, now on three block types)
---------------------------------------------------------------
With `--include-partial-messages` every block arrives twice — incrementally as
`content_block_delta`, then finalised in an `assistant` event. Rendering both would duplicate
the entire run. The rule, applied to thinking, text AND tool_use alike:

  * the block's slot is opened at `content_block_start`, which fixes its POSITION in sequence;
  * deltas accumulate into that slot;
  * the `assistant` event overwrites the slot with the finalised value;
  * a slot never finalised is emitted from its deltas and labelled `[PARTIAL]`.

So a run killed mid-tool-call still shows the half-typed command at the point it was typed,
and a run killed mid-thought still shows the thought. Old transcripts recorded without partial
messages have no deltas at all and simply take the `assistant` path — both shapes work.

SIZE
----
Observed on real phase logs: roughly a hundred KB of tool output per phase, most results a couple
of KB, the largest a few tens of KB. `--max-result-chars` (default 4000) keeps the head and tail of anything longer, because
a long result's *last* lines are usually the ones the reasoning refers to. `0` disables the cap.

USAGE
-----
    python3 extract_thoughts_v2.py <transcript.jsonl> -o run.md
    python3 extract_thoughts_v2.py logs/ --max-result-chars 0 -o run.md   # nothing trimmed
    python3 extract_thoughts_v2.py logs/phase4.jsonl --raw-json           # + source lines
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

_TRUNCATED_TEXT = re.compile(r'"(?:thinking|text|partial_json)"\s*:\s*"((?:[^"\\]|\\.)*)')

RULE = "─" * 70


class Entry:
    """One thing that happened, at the position it happened."""

    __slots__ = ("kind", "text", "tool", "tool_id", "final", "meta")

    def __init__(self, kind: str, tool: str = "", tool_id: str = "") -> None:
        self.kind = kind          # thought | tool_call | tool_result | assistant
        self.text = ""
        self.tool = tool
        self.tool_id = tool_id
        self.final = False        # True once the authoritative copy has landed
        self.meta: Dict[str, object] = {}

    @property
    def partial(self) -> bool:
        return not self.final


def _clip(text: str, limit: int) -> str:
    """Trim the middle, never the ends — the tail of a result is usually the point."""
    if limit <= 0 or len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    dropped = len(text) - limit
    return (f"{text[:head]}\n\n[... {dropped:,} characters trimmed "
            f"(--max-result-chars {limit}) ...]\n\n{text[-tail:]}")


def _result_text(block: dict) -> str:
    """tool_result.content is usually a string, but may be a list of blocks."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for sub in content:
            if isinstance(sub, dict):
                parts.append(sub.get("text") or json.dumps(sub, ensure_ascii=False))
            else:
                parts.append(str(sub))
        return "\n".join(parts)
    return "" if content is None else json.dumps(content, ensure_ascii=False)


def _decode_json_string(body: str) -> str:
    try:
        return json.loads('"' + body + '"')
    except json.JSONDecodeError:
        return body


def _scan_string(raw: str, start: int) -> tuple[str, bool, int]:
    """Read one JSON string from `start`, surviving a buffer that ends inside it.

    Returns (decoded, closed, index_after). Stops at the last WHOLE escape, so a cut landing
    inside `\\u26` or on a trailing backslash decodes what came before instead of raising.
    """
    buf: List[str] = []
    i = start
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            return _decode_json_string("".join(buf)), True, i + 1
        if ch == "\\":
            if i + 1 >= len(raw):
                break                      # cut on the backslash itself
            if raw[i + 1] == "u":
                if i + 6 > len(raw):
                    break                  # cut inside a \uXXXX
                buf.append(raw[i:i + 6]); i += 6; continue
            buf.append(raw[i:i + 2]); i += 2; continue
        buf.append(ch)
        i += 1
    return _decode_json_string("".join(buf)), False, len(raw)


_JSON_KEY = re.compile(r'"([A-Za-z_][A-Za-z_0-9]*)"\s*:\s*"')


def _partial_input(raw: str) -> Dict[str, str]:
    """Rebuild what can be read from a tool call's argument JSON that was cut mid-stream.

    WHY THIS IS NOT AN EDGE CASE: observed across real phase logs, **the large majority of streamed
    characters are tool-call arguments**. A process killed while a block is
    open is almost always inside one — and the packet itself is written by a `Write` call, so
    the single most valuable block in the protocol is exactly this shape.

    Values are read in order, each consumed whole before the next key is sought, so a `"k":"`
    sequence occurring INSIDE a string value cannot be mistaken for a key. Non-string values
    (numbers, booleans, nested objects) are skipped — the fields that matter here (`command`,
    `file_path`, `content`, `pattern`) are all strings.
    """
    out: Dict[str, str] = {}
    i = 0
    while True:
        m = _JSON_KEY.search(raw, i)
        if not m:
            break
        value, closed, end = _scan_string(raw, m.end())
        out[m.group(1)] = value
        if not closed:
            break                          # the buffer ended inside this value
        i = end
    return out


def _describe_input(tool: str, data: object, partial: bool = False) -> str:
    """Render a tool's arguments the way a human reads them."""
    if not isinstance(data, dict):
        return str(data)
    if tool == "Bash" and "command" in data:
        return str(data["command"])
    if tool in ("Read", "Glob", "Grep") and ("file_path" in data or "pattern" in data):
        bits = [f"{k}: {v}" for k, v in data.items() if k != "description"]
        return "\n".join(bits)
    if tool == "Write" and "file_path" in data:
        body = str(data.get("content", ""))
        if partial:
            # The packet is written by a Write. When that call was cut off, this text IS the
            # salvage — the whole reason the harness mirrors it to PHASE_BACKUP. Summarising
            # it to a character count here would throw away the most valuable block in the run.
            return (f"file_path: {data['file_path']}\n"
                    f"--- content as far as it got ({len(body):,} characters) ---\n{body}")
        return f"file_path: {data['file_path']}\n({len(body):,} characters of content)"
    return json.dumps(data, indent=2, ensure_ascii=False)


def parse(path: Path, max_result: int) -> tuple[List[Entry], Dict[str, object]]:
    entries: List[Entry] = []
    meta: Dict[str, object] = {"path": str(path)}
    tool_names: Dict[str, str] = {}       # tool_use_id -> tool name
    open_slot: Optional[Entry] = None     # the content block currently streaming
    raw_lines: Dict[int, str] = {}

    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Transcript cut mid-line by a kill. Salvage the payload into the open slot.
                m = _TRUNCATED_TEXT.search(line)
                if m and open_slot is not None:
                    try:
                        open_slot.text += json.loads('"' + m.group(1) + '"')
                    except json.JSONDecodeError:
                        open_slot.text += m.group(1)
                continue

            etype = event.get("type")

            if etype == "system" and event.get("subtype") == "init":
                for key in ("model", "cwd", "session_id", "permissionMode",
                            "claude_code_version"):
                    if event.get(key) is not None:
                        meta[key] = event[key]

            elif etype == "stream_event":
                ev = event.get("event") or {}
                kind = ev.get("type")

                if kind == "content_block_start":
                    block = ev.get("content_block") or {}
                    btype = block.get("type")
                    if btype == "thinking":
                        open_slot = Entry("thought")
                        entries.append(open_slot)
                    elif btype == "text":
                        open_slot = Entry("assistant")
                        entries.append(open_slot)
                    elif btype == "tool_use":
                        name = block.get("name", "")
                        open_slot = Entry("tool_call", tool=name,
                                          tool_id=block.get("id", ""))
                        if block.get("id"):
                            tool_names[block["id"]] = name
                        entries.append(open_slot)

                elif kind == "content_block_delta" and open_slot is not None:
                    delta = ev.get("delta") or {}
                    dtype = delta.get("type")
                    if dtype == "thinking_delta":
                        open_slot.text += delta.get("thinking", "")
                    elif dtype == "text_delta":
                        open_slot.text += delta.get("text", "")
                    elif dtype == "input_json_delta":
                        open_slot.text += delta.get("partial_json", "")

                elif kind == "content_block_stop":
                    open_slot = None

            elif etype == "assistant":
                message = event.get("message") or {}
                meta.setdefault("model", message.get("model"))
                for block in message.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "thinking":
                        slot = open_slot if (open_slot is not None
                                             and open_slot.kind == "thought") else None
                        if slot is None:
                            slot = Entry("thought")
                            entries.append(slot)
                        slot.text = block.get("thinking", "")
                        slot.final = True
                    elif btype == "text":
                        slot = open_slot if (open_slot is not None
                                             and open_slot.kind == "assistant") else None
                        if slot is None:
                            slot = Entry("assistant")
                            entries.append(slot)
                        slot.text = block.get("text", "")
                        slot.final = True
                    elif btype == "tool_use":
                        name = block.get("name", "")
                        tid = block.get("id", "")
                        if tid:
                            tool_names[tid] = name
                        slot = open_slot if (open_slot is not None
                                             and open_slot.kind == "tool_call") else None
                        if slot is None:
                            slot = Entry("tool_call", tool=name, tool_id=tid)
                            entries.append(slot)
                        slot.tool = name or slot.tool
                        slot.tool_id = tid or slot.tool_id
                        slot.text = _describe_input(name, block.get("input"))
                        slot.final = True
                        slot.meta["description"] = (block.get("input") or {}).get("description") \
                            if isinstance(block.get("input"), dict) else None

            elif etype == "user":
                content = (event.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        entry = Entry("tool_result", tool=tool_names.get(tid, ""), tool_id=tid)
                        body = _result_text(block)
                        entry.meta["chars"] = len(body)
                        entry.meta["is_error"] = bool(block.get("is_error"))
                        entry.text = _clip(body, max_result)
                        entry.final = True
                        entries.append(entry)

            elif etype == "result":
                # `result` holds the model's whole final message on a successful run — a
                # multi-KB answer that has no business in a summary header. Keep one line.
                ended = event.get("result") or event.get("subtype") or ""
                ended = " ".join(str(ended).split())
                meta["ended"] = (ended[:120] + "…") if len(ended) > 120 else ended
                meta["errored"] = bool(event.get("is_error"))
                meta["terminal_reason"] = event.get("terminal_reason")
                meta["num_turns"] = event.get("num_turns")
                meta["cost_usd"] = event.get("total_cost_usd")
                usage = event.get("usage") or {}
                meta["thinking_tokens"] = (usage.get("output_tokens_details") or {}) \
                    .get("thinking_tokens")

            elif etype == "rate_limit_event":
                info = event.get("rate_limit_info") or {}
                if info.get("status") in ("rejected", "exhausted"):
                    meta["rate_limit"] = f"{info.get('rateLimitType')} — {info.get('status')}"

            if lineno in raw_lines:
                pass

    return entries, meta


def render(path: Path, entries: List[Entry], meta: Dict[str, object]) -> str:
    out: List[str] = []
    counts: Dict[str, int] = {}
    for e in entries:
        counts[e.kind] = counts.get(e.kind, 0) + 1

    out.append(f"# Reconstructed run — {path.name}")
    out.append("")
    out.append("The run below is rebuilt from its transcript **in the order it happened**: every")
    out.append("thought, every command, every result. Text is verbatim — nothing is summarised or")
    out.append("reordered. `[PARTIAL]` marks a block the stream ended inside.")
    out.append("")
    facts = []
    for key, label in (("model", "model"), ("session_id", "session"),
                       ("num_turns", "turns"), ("cost_usd", "cost USD"),
                       ("thinking_tokens", "thinking tokens")):
        if meta.get(key) is not None:
            facts.append(f"- **{label}:** {meta[key]}")
    for kind, label in (("thought", "thoughts"), ("tool_call", "tool calls"),
                        ("tool_result", "tool results"), ("assistant", "spoken messages")):
        facts.append(f"- **{label}:** {counts.get(kind, 0)}")
    if meta.get("rate_limit"):
        facts.append(f"- **rate limit hit:** {meta['rate_limit']}")
    if meta.get("ended"):
        how = "FAILED" if meta.get("errored") else "completed"
        facts.append(f"- **{how}:** {meta['ended']}")
    elif entries:
        facts.append("- **no `result` event:** the transcript stops mid-stream — this run was "
                     "cut off rather than finished.")
    out.extend(facts)
    out.append("")

    blank_thoughts = sum(1 for e in entries if e.kind == "thought" and not e.text)
    if blank_thoughts:
        out.append(f"> **{blank_thoughts} thinking block(s) in this run are blank.** The run was")
        out.append("> recorded without `--thinking-display summarized`; the tokens were generated")
        out.append("> and billed, but the text was never returned. The tool calls and results")
        out.append("> below are complete regardless.")
        out.append("")

    n = 0
    for entry in entries:
        if entry.kind == "thought" and not entry.text:
            continue
        n += 1
        tag = "  `[PARTIAL — stream ended here]`" if entry.partial else ""

        if entry.kind == "thought":
            out.append(f"### {n:03d} · THOUGHT{tag}")
            out.append("")
            out.append(entry.text)
        elif entry.kind == "tool_call":
            out.append(f"### {n:03d} · TOOL CALL · {entry.tool or '?'}{tag}")
            out.append("")
            desc = entry.meta.get("description")
            if desc:
                out.append(f"*{desc}*")
                out.append("")
            body = entry.text
            if entry.partial:
                # A finalised call was already rendered by _describe_input; a partial one is
                # still raw argument JSON. Decode it the same way so the two read alike —
                # otherwise the most common death shape is the least legible output.
                fields = _partial_input(body)
                if fields:
                    body = _describe_input(entry.tool, fields, partial=True)
            out.append("```")
            out.append(body)
            out.append("```")
        elif entry.kind == "tool_result":
            size = entry.meta.get("chars", 0)
            err = "  **ERROR**" if entry.meta.get("is_error") else ""
            out.append(f"### {n:03d} · TOOL RESULT · {entry.tool or '?'} "
                       f"({size:,} chars){err}")
            out.append("")
            out.append("```")
            out.append(entry.text)
            out.append("```")
        else:
            out.append(f"### {n:03d} · ASSISTANT{tag}")
            out.append("")
            out.append(entry.text)

        out.append("")
        out.append(RULE)
        out.append("")

    return "\n".join(out) + "\n"


def _first_timestamp(path: Path) -> str:
    """When this run started, from the first event carrying a timestamp.

    Filename order is not run order. A re-run keeps prior attempts by renaming the old log
    (`phase3.jsonl` -> `phase3.200931.jsonl`), so the ORIGINAL sorts before its successor by
    name while being the older run — right by accident there, wrong the moment a resume log
    (`phase3.resume.HHMMSS.jsonl`) joins them. Reconstructing a run in the wrong order is the
    one thing this tool must not do, so order by the clock, not the name.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("timestamp"):
                    return str(event["timestamp"])
    except OSError:
        pass
    return ""


def collect(paths: List[Path]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(p.glob("*.jsonl"))
        elif p.exists():
            files.append(p)
        else:
            print(f"warning: no such path: {p}", file=sys.stderr)
    # A file with no timestamped event sorts to the front; the name breaks remaining ties.
    files.sort(key=lambda f: (_first_timestamp(f), f.name))
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="write the reconstruction here")
    ap.add_argument("--max-result-chars", type=int, default=4000,
                    help="trim the middle of tool results longer than this (0 = no limit)")
    args = ap.parse_args(argv)

    files = collect(args.paths)
    if not files:
        print("no transcripts found", file=sys.stderr)
        return 2

    chunks = []
    for f in files:
        entries, meta = parse(f, args.max_result_chars)
        chunks.append(render(f, entries, meta))
    text = "\n".join(chunks)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(args.out.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, args.out)
        print(f"{args.out}  ({len(text):,} characters, ~{len(text)//4:,} tokens, "
              f"{len(files)} transcript(s))")
    else:
        try:
            sys.stdout.write(text)
        except BrokenPipeError:
            # Piped into `head`/`less` and the reader went away. Not an error.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(main())
