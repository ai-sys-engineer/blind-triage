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

It also writes the phase's packet to disk AS THE MODEL TYPES IT
-----------------------------------------------------------------
Optional, enabled by ``--backup-dir``. Observed in early
cases: several of them lost a phase outright, and the packet — the ONLY artifact
that crosses a phase boundary — is emitted in a single ``Write`` at the very end of a phase
(tens of thousands of chars for one phase 1). Everything the phase measured is held in context until that
instant, so a seven-day limit or a container drop a second earlier costs the whole phase.

With ``--include-partial-messages`` the CLI emits the ``Write`` tool's arguments as
``input_json_delta`` chunks while they are being generated. Reassembling them here means a
death at 80% of the write leaves 80% of the real packet on disk, in the packet's own format.

**Nothing is asked of the model.** It composes the packet wholesale exactly as before — with
whatever back-and-forth between fields it likes — and this file reads over its shoulder. That
is the whole point: the alternative (telling a phase to write section by section) would change
how the packet is composed, and the packet's fields are interdependent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

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


# ─────────────────────────────────────────────────────────────────────────────
# Live packet capture
# ─────────────────────────────────────────────────────────────────────────────

#: Where the growing `content` value starts inside the Write tool's argument JSON. The CLI emits
#: `file_path` before `content`, so by the time the body arrives we already know the target.
_CONTENT_KEY = re.compile(r'"content"\s*:\s*"')
_PATH_KEY = re.compile(r'"file_path"\s*:\s*"')

#: Flush thresholds. Rewriting a 75 KB file every couple of seconds is free; doing it per token
#: is not, and this process sits in the pipe between the model and the human's terminal.
_FLUSH_SECONDS = 2.0
_FLUSH_CHARS = 4096


def _safe_prefix(raw: str) -> Tuple[str, bool]:
    """Longest prefix of a JSON string body that can be decoded, and whether the string ended.

    The buffer is a string literal cut off mid-flight, so it can end inside a ``\\uXXXX`` escape
    or on a lone backslash. Decoding that raises, and a capture that raises on truncation is
    useless precisely when it matters. So walk the escapes and stop at the last whole one.
    """
    i, n, safe = 0, len(raw), 0
    while i < n:
        ch = raw[i]
        if ch == '"':
            return raw[:i], True
        if ch == "\\":
            if i + 1 >= n:
                break                      # trailing backslash: the escape is still arriving
            i += 6 if raw[i + 1] == "u" else 2
            if i > n:
                break                      # \uXX — the code point is half here
        else:
            i += 1
        safe = i
    return raw[:safe], False


def _decode(prefix: str) -> str:
    """Decode a JSON string body, returning '' rather than raising on anything unexpected."""
    try:
        return json.loads('"' + prefix + '"')
    except (json.JSONDecodeError, ValueError):
        return ""


class LiveBackup:
    """Mirrors the phase's packet to disk while it is being written.

    Three files, all harness-written and none of them mentioned to any phase:

    * ``phase<N>_backup.md``    — the packet, reassembled from the Write's argument deltas.
    * ``phase<N>_narration.md`` — the phase's stdout report, which is composed around the write
                                  and therefore survives a death that lands *before* it.
    * ``phase<N>_thinking.md``  — the reasoning trace. Populated whenever the run was launched
                                  with ``--thinking-display summarized`` (see THINKING_ARGS in
                                  blind-triage.sh); absent otherwise, because without that flag
                                  ``thinking_delta`` events arrive with zero characters even
                                  though the tokens were generated and billed.
    """

    def __init__(self, backup_dir: Path, phase: str, packet_path: Optional[str]) -> None:
        self.dir = backup_dir
        self.packet_path = os.path.abspath(packet_path) if packet_path else None
        self.files = {
            "packet": backup_dir / f"phase{phase}_backup.md",
            "narration": backup_dir / f"phase{phase}_narration.md",
            "thinking": backup_dir / f"phase{phase}_thinking.md",
        }
        self.text: Dict[str, str] = {"packet": "", "narration": "", "thinking": ""}
        self._flushed: Dict[str, int] = {"packet": -1, "narration": -1, "thinking": -1}
        self._last_flush = 0.0
        #: content-block index -> accumulated partial JSON for that tool_use
        self._buffers: Dict[int, str] = {}
        #: content-block index -> True once the block is known to be the packet's Write
        self._is_packet: Dict[int, bool] = {}
        backup_dir.mkdir(parents=True, exist_ok=True)

    # -- writing ---------------------------------------------------------------------------
    def _write(self, key: str) -> None:
        body = self.text[key]
        if not body or len(body) == self._flushed[key]:
            return
        target = self.files[key]
        tmp = target.with_suffix(target.suffix + ".tmp")
        # errors="replace": a truncated buffer can end on a lone surrogate half, and losing one
        # character is better than losing the flush.
        with open(tmp, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(body)
        os.replace(tmp, target)
        self._flushed[key] = len(body)

    def flush(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_flush < _FLUSH_SECONDS:
            grown = any(len(self.text[k]) - self._flushed[k] >= _FLUSH_CHARS for k in self.text)
            if not grown:
                return
        self._last_flush = now
        for key in self.text:
            self._write(key)

    # -- stream events ---------------------------------------------------------------------
    def on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                self._buffers[event.get("index", -1)] = ""
            return

        if kind == "content_block_stop":
            self._buffers.pop(event.get("index", -1), None)
            self.flush(force=True)
            return

        if kind != "content_block_delta":
            return

        delta = event.get("delta") or {}
        dtype = delta.get("type")

        if dtype == "text_delta":
            self.text["narration"] += delta.get("text", "")
        elif dtype == "thinking_delta":
            self.text["thinking"] += delta.get("thinking", "")
        elif dtype == "input_json_delta":
            self._on_input_json(event.get("index", -1), delta.get("partial_json", ""))
        else:
            return
        self.flush()

    def _on_input_json(self, index: int, chunk: str) -> None:
        if index not in self._buffers:
            return
        buf = self._buffers[index] + chunk
        self._buffers[index] = buf

        # Decide once whether this Write is the packet. file_path arrives before content, so the
        # decision is made before a single byte of the body has to be buffered speculatively.
        if index not in self._is_packet:
            match = _PATH_KEY.search(buf)
            if not match:
                return
            path, done = _safe_prefix(buf[match.end():])
            if not done:
                return                      # path still arriving; ask again on the next chunk
            self._is_packet[index] = self._targets_packet(_decode(path))

        if not self._is_packet.get(index):
            return
        match = _CONTENT_KEY.search(buf)
        if not match:
            return
        prefix, _ = _safe_prefix(buf[match.end():])
        self.text["packet"] = _decode(prefix)

    def _targets_packet(self, path: str) -> bool:
        if not path:
            return False
        path = os.path.abspath(path)
        if self.packet_path and path == self.packet_path:
            return True
        # A phase that writes its deliverable to a different name in packets/ (phase4-plan.md, or
        # a bounce writing a variant) is still worth capturing. PHASE_BACKUP is excluded so the
        # capture can never read its own output back in.
        parent = os.path.dirname(path)
        return (
            self.packet_path is not None
            and parent == os.path.dirname(self.packet_path)
            and path.endswith(".md")
        )


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--phase", default="")
    parser.add_argument("--packet", default="")
    args, _unknown = parser.parse_known_args(argv)
    return args


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    backup = None
    if args.backup_dir and args.phase:
        try:
            backup = LiveBackup(Path(args.backup_dir), args.phase, args.packet or None)
        except OSError:
            # An unwritable backup dir must never take the phase down with it. The formatter's
            # standing contract applies to the capture too: informational, never fatal.
            backup = None

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

        if kind == "stream_event":
            # The partial-message channel. It is never displayed — it would spray the terminal
            # with every token — it only feeds the on-disk backup.
            if backup is not None:
                try:
                    backup.on_event(event.get("event") or {})
                except Exception:
                    backup = None      # capture is insurance; it never takes a phase down
            continue

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

    if backup is not None:
        backup.flush(force=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
