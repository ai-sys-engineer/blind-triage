#!/usr/bin/env python3
"""Pretty-print Claude Code's ``--output-format stream-json`` for a human watching live.

Why this exists
---------------
``claude -p`` with plain text output prints **nothing** until the whole phase is finished. A
blind-triage phase runs audit instruments for minutes, and the human's job during Phase 1 is to
*watch for a named cause* — which they cannot do staring at a blank terminal.

So the driver asks for the JSONL event stream instead and pipes it through here. Every event is
echoed to the raw log untouched (the driver's ``tee`` does that); this filter only decides what a
person sees.

Contract: JSONL on stdin, human-readable text on stdout, exit 0 unless stdin is unreadable.
Unknown event shapes are ignored rather than fatal — the stream format grows between CLI versions
and a formatter must never be the thing that kills a phase.
"""
from __future__ import annotations

import json
import os
import sys

# Colour only when a human is actually looking. NO_COLOR is honoured by convention.
_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


DIM, BOLD, CYAN, YELLOW, RED, GREEN = "2", "1", "36", "33", "31", "32"

#: Tool inputs worth showing, in the order we look for them. A tool call is only useful to a
#: watcher if they can see WHICH file or command it touched.
_INPUT_KEYS = ("command", "file_path", "pattern", "path", "target", "skill", "description")


def _tool_detail(tool_input: dict) -> str:
    for key in _INPUT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            first_line = value.strip().splitlines()[0]
            return first_line if len(first_line) <= 160 else first_line[:157] + "..."
    return ""


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw or not raw.startswith("{"):
            # Non-JSON noise (e.g. the trust-dialog warning) is passed through verbatim so a
            # misconfiguration is visible rather than swallowed.
            if raw:
                print(_c(DIM, raw), flush=True)
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        kind = event.get("type")

        if kind == "system" and event.get("subtype") == "init":
            model = event.get("model", "?")
            session = event.get("session_id", "?")
            mode = event.get("permissionMode", "?")
            print(_c(DIM, f"  ├─ model={model}  mode={mode}  session={session}"), flush=True)

        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []) or []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    print(block["text"], flush=True)
                elif block.get("type") == "tool_use":
                    detail = _tool_detail(block.get("input") or {})
                    label = _c(CYAN, f"  ⚙ {block.get('name', 'tool')}")
                    print(f"{label} {_c(DIM, detail)}" if detail else label, flush=True)

        elif kind == "user":
            # Only surface tool RESULTS that failed; successful output is usually huge and the
            # model is about to summarise it anyway.
            for block in event.get("message", {}).get("content", []) or []:
                if block.get("type") == "tool_result" and block.get("is_error"):
                    body = block.get("content")
                    if isinstance(body, list):
                        body = " ".join(
                            part.get("text", "") for part in body if isinstance(part, dict)
                        )
                    body = str(body or "").strip().splitlines()
                    print(_c(RED, f"  ✗ tool error: {body[0] if body else 'unknown'}"), flush=True)

        elif kind == "result":
            cost = event.get("total_cost_usd")
            secs = (event.get("duration_ms") or 0) / 1000.0
            turns = event.get("num_turns", "?")
            denials = event.get("permission_denials") or []
            tone = RED if event.get("is_error") else GREEN
            summary = f"  └─ done in {secs:.0f}s · {turns} turns"
            if isinstance(cost, (int, float)):
                summary += f" · ${cost:.2f}"
            print(_c(tone, summary), flush=True)
            if denials:
                # These matter: a denied tool means the phase ran with a hole in it. The driver
                # cannot see them (it only reads the packet), so the human must.
                names = ", ".join(sorted({d.get("tool_name", "?") for d in denials}))
                print(_c(YELLOW, f"  !  {len(denials)} permission denial(s): {names}"), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
