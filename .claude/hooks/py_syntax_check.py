#!/usr/bin/env python3
"""PostToolUse hook: byte-cheap syntax check for a just-edited Python file.

Runs `py_compile` on the file an Edit/Write tool touched. This is deterministic
and costs ZERO model tokens — it is a machine gate, not a model "doing QA".
Exit 2 surfaces the syntax error back to the active model as feedback; exit 0
otherwise. The hook never blocks on its own internal problems (missing/garbled
input, non-Python files) so it can't wedge the session.
"""
from __future__ import annotations

import json
import py_compile
import sys


def main() -> int:
    """Read the hook payload from stdin and syntax-check the edited file."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not isinstance(file_path, str) or not file_path.endswith(".py"):
        return 0

    try:
        py_compile.compile(file_path, doraise=True)
    except py_compile.PyCompileError as exc:
        print(f"[py_compile] syntax error in {file_path}:\n{exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
