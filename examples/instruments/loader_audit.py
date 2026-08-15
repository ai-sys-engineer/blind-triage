#!/usr/bin/env python3
"""loader_audit — what a record holds, beside what its loader hands downstream.

The third boundary
------------------
``render_audit`` diffs a record against text built from it. ``projection_audit`` diffs a record
against the sibling record derived from it. Neither sees the boundary in between: a **loader** that
reads a record and builds a plain dict from a subset of its columns. Everything downstream then
consumes the dict, and the columns the loader declined to copy are gone — not narrowed by a schema
anyone declared, just absent from a literal.

This is the highest-leverage of the three boundaries and the least visible. A schema drop
(``projection_audit``) at least leaves a table definition someone can read. A loader drop leaves
nothing but the shape of a dict literal in one function, and every consumer inherits it silently.

MEASUREMENTS, NEVER A VERDICT
-----------------------------
Inherited from ``run_forensics`` / ``render_audit``. Loaders narrow on purpose all the time — that
is what a loader is for. This prints which columns do not make the trip. Ruling on any row is the
human's.

The false positive this tool refuses to make
--------------------------------------------
A thin wrapper that delegates (``return _other_module_load(project_id)``) reads **zero** record
fields. Naively that looks like "drops every column", and a codebase following the single-source
reader discipline is full of such wrappers — so a naive version of this tool opens with a screenful
of confident nonsense and is never trusted again.

A function reading no record fields is **not a projection site**. It is reported as *delegates /
reads no record*, mirroring ``render_audit``'s existing "source pre-projected by caller" bucket.

Renames are carries
-------------------
``{"parameters": params}`` where ``params = json.loads(r.parameters_json)`` carries
``parameters_json`` under a new name. The shared alias resolution in ``_AccessCollector`` follows
that, and it is correct: the datum crossed the boundary. Only a column that reaches no dict value at
all is dropped.

Usage::

    cd src && python tools/loader_audit.py
    cd src && python tools/loader_audit.py --target <module>:<function>
    cd src && python tools/loader_audit.py --carried    # list the columns that DO cross

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
    _MIN_OVERLAP,
    _AccessCollector,
    _rel,
    collect_record_schemas,
    match_records,
)

_SRC = _HERE.parent

#: Name fragments marking a function whose job is to read records out of storage. Disclosed in the
#: output so the reader can distrust the selection.
_LOADER_HINTS: Tuple[str, ...] = ("load", "fetch", "read_", "_rows", "select")


def looks_like_loader(name: str) -> bool:
    """Return whether a function name matches the disclosed loader selection rule."""
    lowered = name.lower()
    return any(hint in lowered for hint in _LOADER_HINTS)


def _selected_records(node: ast.FunctionDef, known: Set[str]) -> List[str]:
    """Return record classes named in a ``select(X)`` call — the strongest source signal."""
    out: List[str] = []
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "select"):
            for arg in sub.args:
                if isinstance(arg, ast.Name) and arg.id in known and arg.id not in out:
                    out.append(arg.id)
    return out


def analyze_loader(
    node: ast.FunctionDef, schemas: Dict[str, Dict[str, List[str]]]
) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """Diff a record against the dict a loader builds from it (pure).

    Args:
        node: The parsed loader function.
        schemas: Output of :func:`render_audit.collect_record_schemas`.

    Returns:
        ``(finding, reason)``. ``reason`` is non-None when no diff was possible, and its two values
        are different findings: a function reading no record fields **delegates** (audit its callee
        instead), while one whose reads match no declared class is building from an ad-hoc shape.
    """
    collector = _AccessCollector(slot_kind="dict")
    for stmt in node.body:
        collector.visit(stmt)

    if not collector.referenced:
        return None, "delegates / reads no record fields"

    known = set(schemas)
    selected = [r for r in _selected_records(node, known) if r in schemas]
    if selected:
        source = selected[0]
        overlap = len(collector.referenced & set(schemas[source]["fields"]))
        basis = "select() call"
    else:
        ranked = match_records(collector.referenced, schemas)
        if not ranked:
            return None, (f"source shape not declared by any class "
                          f"({len(collector.referenced)} field-ish names read)")
        source, overlap = ranked[0]
        basis = f"{overlap} field names in common"

    fields = [f for f in schemas[source]["fields"] if f not in _HOUSEKEEPING]
    carried = [f for f in fields if f in collector.rendered]
    if not carried:
        return None, "reads the record but builds no dict from it (not a projection site)"

    return {
        "source": source,
        "basis": basis,
        "overlap": overlap,
        "lineno": node.lineno,
        "fields": fields,
        "carried": carried,
        "dropped": [f for f in fields if f not in collector.rendered],
    }, None


def audit_file(path: Path) -> List[Dict[str, object]]:
    """Return structured loader findings for one module (the programmatic entry point).

    Used by the ``render_boundary_notice`` hook so the loader diff arrives when the file is opened.

    Args:
        path: A python file to audit.

    Returns:
        ``[{"function", "lineno", "finding", "reason"}]``; empty when the module has no loaders.
        Never raises — an unparseable file yields ``[]``.
    """
    try:
        scan = sorted(_SRC.glob("*.py")) + sorted(_SRC.glob("crews/**/*.py"))
        scan = [p for p in scan if "deliverables" not in p.parts and "tests" not in p.parts]
        schemas = collect_record_schemas(scan)
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return []

    out: List[Dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not looks_like_loader(node.name):
            continue
        finding, reason = analyze_loader(node, schemas)
        if finding is None and reason and "delegates" in reason:
            continue  # a wrapper is not a finding; audit its callee instead
        if finding is None:
            continue
        if not finding["dropped"]:
            continue
        out.append({"function": node.name, "lineno": node.lineno,
                    "finding": finding, "reason": reason})
    return out


def report(module: str, func: str, finding: Dict[str, object], show_carried: bool) -> None:
    """Print one loader table."""
    print(f"\n{'=' * 84}")
    print(f"{module}:{func}  (line {finding['lineno']})   {finding['source']}  ->  dict")
    print(f"{'=' * 84}")
    print(f"  source identified by: {finding['basis']}")

    carried = set(finding["carried"])  # type: ignore[arg-type]
    print(f"\n  {'source column':<32} {'reaches the dict?'}")
    print(f"  {'-' * 32} {'-' * 20}")
    for field in finding["fields"]:  # type: ignore[union-attr]
        if field in carried and not show_carried:
            continue
        print(f"  {field:<32} {'carried' if field in carried else 'DROPPED'}")
    print(f"\n  {len(carried)} of {len(finding['fields'])} columns cross; "  # type: ignore[arg-type]
          f"{len(finding['dropped'])} dropped.")  # type: ignore[arg-type]
    print("  Every consumer of this loader inherits the omission.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns 0 always — this tool reports, it never passes or fails."""
    parser = argparse.ArgumentParser(
        description="Print what a record holds beside what its loader hands downstream.")
    parser.add_argument("--target", action="append", default=[],
                        help="Only audit 'module:function' (repeatable).")
    parser.add_argument("--carried", action="store_true",
                        help="Also list the columns that DO cross (default: only those that don't).")
    parser.add_argument("--show-skipped", action="store_true",
                        help="List loaders no diff was possible for, and why.")
    args = parser.parse_args(argv)

    scan = sorted(_SRC.glob("*.py")) + sorted(_SRC.glob("crews/**/*.py"))
    scan = [p for p in scan if "deliverables" not in p.parts and "tests" not in p.parts]
    schemas = collect_record_schemas(scan)

    print("loader_audit — record -> in-memory dict boundaries")
    print(f"  selection rule : function name contains one of {list(_LOADER_HINTS)}")
    print(f"  record schemas : {len(schemas)} classes across {len(scan)} modules")
    print(f"  source id'd by : a select() call, else >= {_MIN_OVERLAP} field names in common")
    print(f"  columns hidden : {sorted(_HOUSEKEEPING)} (row identity / capture metadata)")
    print("\n  Loaders narrow on purpose — this prints which columns do not make the trip,")
    print("  never whether they should. A delegating wrapper is not a projection site.")

    seen = 0
    skipped: List[Tuple[str, str]] = []
    for path in scan:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        module = _rel(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not looks_like_loader(node.name):
                continue
            if args.target and not any(
                    module.endswith(t.partition(":")[0]) and node.name == t.partition(":")[2]
                    for t in args.target):
                continue
            finding, reason = analyze_loader(node, schemas)
            if reason:
                skipped.append((f"{module}:{node.name}", reason))
                continue
            if not finding["dropped"]:  # type: ignore[index]
                skipped.append((f"{module}:{node.name}", "carries every column"))
                continue
            report(module, node.name, finding, args.carried)  # type: ignore[arg-type]
            seen += 1

    print(f"\n{'=' * 84}")
    print(f"{seen} loader(s) where a source column does not reach the dict.")
    if skipped and args.show_skipped:
        print(f"\nno diff ({len(skipped)}):")
        for item, reason in sorted(skipped, key=lambda t: (t[1], t[0])):
            print(f"  {item:<52} {reason}")
    elif skipped:
        print(f"({len(skipped)} loader(s) reported no diff; --show-skipped to list them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
