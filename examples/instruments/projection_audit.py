#!/usr/bin/env python3
"""projection_audit — what record A holds, beside what record B has room for.

Why this tool exists (the half ``render_audit`` structurally cannot see)
------------------------------------------------------------------------
``render_audit`` diffs a record against the text built from it. That catches a field the
brief declines to print. It cannot catch a field that **is not in the record by the time the
brief runs** — if the intermediate table never had the column, there is nothing at the render
boundary to diff, and the render looks complete.

The chained shape, in the abstract: a capture table records a rich row; a derived sibling table
is built from it holding only the few columns its own job needs; a brief renders that sibling
**faithfully and completely**. Every stage is locally correct. The consumer of the brief is
nonetheless missing a fact that was captured, persisted, and thrown away one table upstream —
and because the render is complete with respect to what it was given, a render-boundary audit
returns clean.

``CLAUDE.md`` calls this shape ``369be0c``: *"one loader never projected one column that sat in
the vault the whole time, the failure surfaced three steps downstream, and every fix went where
the log pointed."* Nothing throws, no test goes red, and the column is absent from every log —
because absence is what it is.

How the pairs are found — schema shape, deliberately NOT dataflow
-----------------------------------------------------------------
The first draft of this tool traced the constructor's enclosing function and found nothing. The
persist helpers here are typically handed their key values **already projected by the caller**,
so at the construction site the source table is not in scope at all. Following values across
call boundaries is exactly the kind of analysis that fails quietly on the case you need it for.

So pairing uses the schemas instead. Two persisted tables that share an identifying key are a
projection pair by construction — the sibling tables in ``db_models`` say so in their own
docstrings, being keyed to "reconcile back" to the table they derive from. That relationship is
visible in the column lists alone, with no call graph, so it cannot be defeated by an extra
layer of indirection.

MEASUREMENTS, NEVER A VERDICT
-----------------------------
Inherited from ``run_forensics`` / ``render_audit``. Narrowing is usually correct and usually
deliberate: a demand table SHOULD be demand-shaped, and most of these columns are absent on
purpose. This prints which columns have nowhere to land. Ruling on any row is the human's.

Usage::

    cd src && python tools/projection_audit.py
    cd src && python tools/projection_audit.py --source <UpstreamRecord>
    cd src && python tools/projection_audit.py --min-shared 3   # tighten pairing

Pure, offline, read-only: parses source with ``ast``, imports and executes nothing.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from render_audit import (  # noqa: E402
    _HOUSEKEEPING,
    MIN_SHARED_KEYS,
    RECORD_MODULE as _RECORD_MODULE,
    collect_record_schemas,
    pair_records,
)

_SRC = _HERE.parent


def find_construction_sites(paths: Sequence[Path], known: Set[str]) -> Dict[str, List[str]]:
    """Locate where each record class is constructed (an annotation, not the analysis).

    Args:
        paths: Python files to scan.
        known: Record class names to look for.

    Returns:
        ``{ClassName: ["module.py:function:line", ...]}``.
    """
    sites: Dict[str, List[str]] = {}
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        module = str(path.relative_to(_SRC))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id in known):
                    sites.setdefault(sub.func.id, []).append(
                        f"{module}:{node.name}:{sub.lineno}")
    return sites


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns 0 always — this tool reports, it never passes or fails."""
    parser = argparse.ArgumentParser(
        description="Print the columns a source record holds that its sibling record cannot store.")
    parser.add_argument("--source", action="append", default=[],
                        help="Only report pairs with this source record (repeatable).")
    parser.add_argument("--min-shared", type=int, default=MIN_SHARED_KEYS,
                        help=f"Shared non-housekeeping columns required to pair (default "
                             f"{MIN_SHARED_KEYS}).")
    args = parser.parse_args(argv)

    scan = sorted(_SRC.glob("*.py")) + sorted(_SRC.glob("crews/**/*.py"))
    scan = [p for p in scan if "deliverables" not in p.parts and "tests" not in p.parts]
    schemas = collect_record_schemas(scan)
    pairs = pair_records(schemas, args.min_shared)
    if args.source:
        pairs = [p for p in pairs if p[0] in args.source]
    sites = find_construction_sites(scan, {p[1] for p in pairs})

    print("projection_audit — record -> record boundaries")
    print(f"  records        : {_RECORD_MODULE} classes only (persisted vault records)")
    print(f"  pairing rule   : >= {args.min_shared} shared non-housekeeping columns")
    print(f"  columns hidden : {sorted(_HOUSEKEEPING)} (row identity / capture metadata)")
    print(f"  pairs found    : {len(pairs)}")
    print("\n  Narrowing is usually deliberate — this prints which columns have nowhere to land,")
    print("  never whether they should. Both directions are shown; the code decides which is")
    print("  upstream.")

    for source, target, shared, only in pairs:
        print(f"\n{'=' * 84}")
        print(f"{source}  ->  {target}")
        print(f"{'=' * 84}")
        print(f"  paired on shared column(s): {', '.join(shared)}")
        where = sites.get(target, [])
        if where:
            print(f"  {target} constructed at: {', '.join(where[:3])}"
                  f"{f' (+{len(where) - 3} more)' if len(where) > 3 else ''}")
        print(f"\n  {source} column(s) with NO column on {target} ({len(only)}):")
        for field in only:
            print(f"    {field}")

    print(f"\n{'=' * 84}")
    print(f"{len(pairs)} pair(s) reported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
