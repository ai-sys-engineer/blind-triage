#!/usr/bin/env python3
"""render_audit — what a record HOLDS, beside what its brief actually PRINTS.

Why this tool exists
--------------------
A field that is captured, persisted, and then silently dropped where model-facing text is
built is invisible in every log. Nothing throws, nothing fails, no test goes red — the
brief simply does not mention it, and a brief is only ever read for what IS there. That
asymmetry is why the class survives inspection: an omission occupies no line on screen
until you put the source columns next to the rendered ones, at which point it occupies a
row and becomes a thing you can see.

This tool builds that two-column table mechanically, so finding an instance does not
depend on anyone noticing an absence.

Scope — one of the four model-facing channels
---------------------------------------------
``.claude/rules/gate-symmetry.md`` names four places the model's context comes from:

1. task text in ``crews/*/config/tasks.yaml``
2. field descriptions on the output schema in ``crews/*/models.py``
3. whatever a tool hands back as text
4. **briefs built in python** ← this tool audits channel 4

Channels 1-3 are out of scope and are NOT covered by a clean run here. Point ``--target``
at a specific function to audit any other text-builder (e.g. a tool's flatten).

DESIGN RULE — MEASUREMENTS, NEVER A VERDICT
-------------------------------------------
Inherited verbatim from ``run_forensics``. **This tool does not diagnose.** A dropped
field is not automatically a defect: this repo deliberately withholds data from makers —
grading labels are kept out of briefs on purpose, so a maker picks the better part rather
than the better-documented one (``CLAUDE.md`` → *Keep the maker blind to the checker*).
Only a human holding the design intent can rule on any given row.

So the output carries field names, counts and the selection rule used. It does not carry
"suspect", "missing", "should", "bug", or severity of any kind. It prints a table and
stops.

Reading the output
------------------
Three buckets per record, and the middle one is the interesting shape:

* ``RENDERED`` — reaches an interpolation slot in the emitted text.
* ``REFERENCED, NOT RENDERED`` — the function reads it (sorting, filtering, a lookup key)
  and never prints it. The data was in the function's hands.
* ``NOT REFERENCED`` — the function never touches it.

Usage::

    cd src && python tools/render_audit.py                  # every channel-4 brief
    cd src && python tools/render_audit.py --target <module>:<function>
    cd src && python tools/render_audit.py --show-skipped   # disclose what was not scanned

Pure, offline, read-only: it parses source with ``ast`` and never imports, executes or
connects to anything.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

_SRC = Path(__file__).resolve().parent.parent

#: Selection rule for channel-4 text builders, disclosed in the output header. A function
#: qualifies when its name matches one of these AND its body contains an f-string.
_NAME_PREFIXES: Tuple[str, ...] = ("format_", "compose_")
_NAME_CONTAINS: Tuple[str, ...] = ("brief",)

#: Bookkeeping columns excluded from the report. Disclosed in the header so the reader can
#: distrust the selection: these are row identity and capture metadata, never brief content.
_HOUSEKEEPING: Set[str] = {"id", "project_id", "iteration_idx", "captured_at", "slot_index"}

#: Minimum overlapping field names before a record type is reported as a function's source.
_MIN_OVERLAP: int = 2

#: Sub-keys of the stringified EpistemicFloat convention (``Field(default="{}")``). A
#: render that reaches the block but never names these emits the number without the
#: sentence that says what the number is for.
_EPISTEMIC_SUBKEYS: Tuple[str, ...] = ("justification", "provenance")


# --- Schema side: what the records hold --------------------------------------

def collect_record_schemas(paths: Sequence[Path]) -> Dict[str, Dict[str, List[str]]]:
    """Read every class's declared field names out of the given modules (pure, ast-only).

    Args:
        paths: Python files to parse for class definitions.

    Returns:
        ``{ClassName: {"fields": [...], "epistemic": [...], "module": "..."}}``, where
        ``epistemic`` lists the fields declared with a ``"{}"`` default — this repo's
        stringified-EpistemicFloat convention.
    """
    schemas: Dict[str, Dict[str, List[str]]] = {}
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            fields: List[str] = []
            epistemic: List[str] = []
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                name = stmt.target.id
                fields.append(name)
                if _declares_empty_dict_default(stmt.value):
                    epistemic.append(name)
            if fields:
                schemas[node.name] = {
                    "fields": fields,
                    "epistemic": epistemic,
                    "module": [_rel(path)],
                }
    return schemas


def _rel(path: Path) -> str:
    """Return ``path`` relative to ``src/``, or its name when it lies outside.

    ``Path.relative_to`` RAISES rather than returning a fallback, so a caller handing in a
    relative or out-of-tree path used to take down the whole scan. Callers include the hook,
    which receives whatever path the tool payload carried.
    """
    try:
        return str(path.resolve().relative_to(_SRC))
    except ValueError:
        return path.name


def _declares_empty_dict_default(value: Optional[ast.expr]) -> bool:
    """Return whether an annotated assignment defaults to the string ``"{}"``."""
    if value is None:
        return False
    for node in ast.walk(value):
        if isinstance(node, ast.Constant) and node.value == "{}":
            return True
    return False


# --- Render side: what the brief prints --------------------------------------

class _AccessCollector(ast.NodeVisitor):
    """Collect record-field accesses, split by whether they reach an interpolation slot.

    Two sets are gathered because they answer different questions. ``referenced`` is every
    field name the function touches at all; ``rendered`` is the subset that reaches an
    f-string ``{...}`` slot. A field in the difference between them was in the function's
    hands and did not reach the text — which is a distinction no grep can draw.

    Local aliases are resolved: ``mpn = getattr(row, "mpn", "")`` followed by
    ``f"{mpn}"`` counts ``mpn`` as rendered, and the alias map is applied transitively so
    ``peak = max(_v(getattr(r, "a")), _v(getattr(r, "b")))`` renders both ``a`` and ``b``.
    """

    def __init__(self, slot_kind: str = "fstring", targets: Set[str] = frozenset()) -> None:
        """Args:
            slot_kind: ``"fstring"`` counts an f-string ``{...}`` slot as the far side of the
                boundary (the render boundary). ``"kwargs"`` counts the keyword arguments of a
                call to one of ``targets`` instead (the projection boundary, where one record is
                constructed from another). One extraction, two boundaries — a second copy of this
                walker would be free to disagree with the first.
            targets: Constructor names treated as the far side when ``slot_kind='kwargs'``.
        """
        self.referenced: Set[str] = set()
        self.rendered: Set[str] = set()
        self.aliases: Dict[str, Set[str]] = {}
        self._slot_kind = slot_kind
        self._targets = set(targets)
        self._depth = 0  # >0 while inside the far side of the boundary

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if self._slot_kind != "fstring":
            self.generic_visit(node)
            return
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Dict(self, node: ast.Dict) -> None:
        """In ``dict`` mode a dict literal's VALUES are the far side of the boundary.

        Keys are excluded deliberately: a key is the name the projection gives a field, not a read
        of it. ``{"description": r.summary}`` carries ``summary``, not ``description``.
        """
        if self._slot_kind != "dict":
            self.generic_visit(node)
            return
        for key in node.keys:
            if key is not None:
                self.visit(key)
        self._depth += 1
        for value in node.values:
            self.visit(value)
        self._depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        fields = _fields_in(node.value)
        names = _local_names_in(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                bound = set(fields)
                for alias in names:
                    bound |= self.aliases.get(alias, set())
                if bound:
                    self.aliases[target.id] = self.aliases.get(target.id, set()) | bound
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if self._depth and node.id in self.aliases:
            self.rendered |= self.aliases[node.id]
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._record(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _callee_name(node.func)
        if name == "getattr" and len(node.args) >= 2:
            self._literal(node.args[1])
        elif name == "get" and node.args:
            self._literal(node.args[0])
        # A called attribute is a METHOD (`s.strip()`, `parts.append(...)`), never a field.
        # Recording it inflates the match and invents overlap that is not there, so descend
        # past the callee name into its receiver and arguments instead of visiting it.
        if isinstance(node.func, ast.Attribute):
            self.visit(node.func.value)
        else:
            self.visit(node.func)

        # In projection mode a call to a record class IS the boundary: everything passed to it
        # crossed, everything else in the enclosing function did not.
        crossing = self._slot_kind == "kwargs" and name in self._targets
        if crossing:
            self._depth += 1
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)
        if crossing:
            self._depth -= 1

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._literal(node.slice)
        self.generic_visit(node)

    def _literal(self, node: ast.expr) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self._record(node.value)

    def _record(self, name: str) -> None:
        self.referenced.add(name)
        if self._depth:
            self.rendered.add(name)


def _callee_name(func: ast.expr) -> str:
    """Return the bare callee name for ``f(...)`` or ``x.f(...)``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _fields_in(node: ast.expr) -> Set[str]:
    """Return every field-ish name accessed anywhere in an expression."""
    collector = _AccessCollector()
    collector.visit(node)
    return collector.referenced


def _local_names_in(node: ast.expr) -> Set[str]:
    """Return the bare local variable names read in an expression."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _has_fstring(node: ast.FunctionDef) -> bool:
    """Return whether a function body contains an f-string."""
    return any(isinstance(n, ast.JoinedStr) for n in ast.walk(node))


def _mentions(node: ast.FunctionDef, needle: str) -> bool:
    """Return whether any string constant in the function contains ``needle``."""
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and needle in n.value
        for n in ast.walk(node)
    )


# --- Selection ---------------------------------------------------------------

def qualifies(name: str) -> bool:
    """Return whether a function name matches the disclosed channel-4 selection rule."""
    return name.startswith(_NAME_PREFIXES) or any(t in name.lower() for t in _NAME_CONTAINS)


def find_text_builders(paths: Sequence[Path]) -> List[Tuple[str, str, ast.FunctionDef]]:
    """Return ``(module, function, node)`` for every function matching the selection rule.

    Args:
        paths: Python files to scan.

    Returns:
        One entry per qualifying function that also contains an f-string.
    """
    found: List[Tuple[str, str, ast.FunctionDef]] = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        module = _rel(path).replace("/", ".")[:-3]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and qualifies(node.name):
                if isinstance(node, ast.FunctionDef) and _has_fstring(node):
                    found.append((module, node.name, node))
    return found


def match_records(
    referenced: Set[str], schemas: Dict[str, Dict[str, List[str]]]
) -> List[Tuple[str, int]]:
    """Rank record types by how many of their fields the function touches.

    Args:
        referenced: Field names accessed anywhere in the function.
        schemas: Output of :func:`collect_record_schemas`.

    Returns:
        ``[(ClassName, overlap_count)]`` sorted by overlap, for records clearing
        :data:`_MIN_OVERLAP`.
    """
    scored: List[Tuple[str, int]] = []
    for name, spec in schemas.items():
        overlap = len(referenced & set(spec["fields"]))
        if overlap >= _MIN_OVERLAP:
            scored.append((name, overlap))
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


# --- Record-to-record pairing (shared with projection_audit) ------------------
#
# Lives here, not in projection_audit, for one mechanical reason: projection_audit imports from
# THIS module, so importing back would be a cycle. Both this and match_records are pure
# "relate records by their columns" helpers, so they belong side by side regardless.

MIN_SHARED_KEYS: int = 2
"""Non-housekeeping columns two records must share before they are treated as a projection pair.

Housekeeping alone (``project_id`` + ``iteration_idx``) is carried by nearly every vault table and
would pair all of them with all of them.
"""

RECORD_MODULE: str = "db_models.py"
"""The module whose classes are persisted vault records.

Pairing is restricted to these: a transient verdict class narrowing its input is a summary, not a
projection.
"""


def pair_records(
    schemas: Dict[str, Dict[str, List[str]]], min_shared: int = MIN_SHARED_KEYS
) -> List[Tuple[str, str, List[str], List[str]]]:
    """Find projection pairs and the source columns with no home in the target (pure).

    Args:
        schemas: Output of :func:`collect_record_schemas`.
        min_shared: Non-housekeeping columns two records must share to be paired.

    Returns:
        ``[(source, target, shared_keys, source_only_columns)]``, largest gap first. BOTH
        directions of a pair are returned — which record is upstream is a fact about the code, not
        about the column lists, so this declines to guess.
    """
    records = {
        name: spec for name, spec in schemas.items()
        if RECORD_MODULE in spec.get("module", [""])[0]
    }
    out: List[Tuple[str, str, List[str], List[str]]] = []
    for a_name, a_spec in records.items():
        a_fields = [f for f in a_spec["fields"] if f not in _HOUSEKEEPING]
        for b_name, b_spec in records.items():
            if a_name == b_name:
                continue
            b_fields = set(b_spec["fields"])
            shared = [f for f in a_fields if f in b_fields]
            if len(shared) < min_shared:
                continue
            only = [f for f in a_fields if f not in b_fields]
            if only:
                out.append((a_name, b_name, shared, only))
    out.sort(key=lambda t: (-len(t[3]), t[0], t[1]))
    return out


def upstream_of(
    record: str, schemas: Dict[str, Dict[str, List[str]]]
) -> List[Tuple[str, List[str]]]:
    """Return records that hold columns ``record`` lacks, i.e. of which it is a narrowed copy.

    This is what stops a clean render diff from reading as an all-clear. A brief can render its
    source record completely and still starve its reader, because the *record* was narrowed one
    step earlier — and at the render boundary there is then nothing left to diff.

    Args:
        record: The record class the render was diffed against.
        schemas: Output of :func:`collect_record_schemas`.

    Returns:
        ``[(upstream_record, columns_it_holds_that_record_lacks)]``, largest gap first.
    """
    return [
        (source, only) for source, target, _shared, only in pair_records(schemas)
        if target == record
    ]


# --- Report ------------------------------------------------------------------

def analyze(
    node: ast.FunctionDef, schemas: Dict[str, Dict[str, List[str]]]
) -> Tuple[List[Dict[str, object]], Optional[str]]:
    """Compute the source-vs-rendered split for one text builder (pure).

    THE single computation behind both presenters — the CLI table below and
    :func:`audit_file`, which the ``render_boundary_notice`` hook calls. Kept as one
    function on purpose: two copies of "which fields reach the text" would be free to
    disagree, which is the defect class this whole tool exists to surface.

    Args:
        node: The parsed function.
        schemas: Record schemas to match against.

    Returns:
        ``(findings, reason)``. ``findings`` holds one dict per matched record type;
        ``reason`` is non-None only when no record matched and no diff was possible.
    """
    collector = _AccessCollector()
    for stmt in node.body:
        collector.visit(stmt)

    matches = match_records(collector.referenced, schemas)
    if not matches:
        if not collector.referenced:
            return [], "source pre-projected by caller (function reads no record fields)"
        return [], (f"source shape not declared by any class "
                    f"({len(collector.referenced)} field-ish names read)")

    findings: List[Dict[str, object]] = []
    for record, overlap in matches:
        spec = schemas[record]
        fields = [f for f in spec["fields"] if f not in _HOUSEKEEPING]
        epistemic_rendered = [f for f in spec["epistemic"] if f in collector.rendered]
        findings.append({
            "record": record,
            "overlap": overlap,
            # Reported even when the column diff below is empty: "this render is faithful" and
            # "this render carries what its reader needs" are different claims, and only the first
            # is in evidence here.
            "upstream": upstream_of(record, schemas),
            "fields": fields,
            "rendered": [f for f in fields if f in collector.rendered],
            "referenced_not_rendered": [
                f for f in fields
                if f in collector.referenced and f not in collector.rendered
            ],
            "not_referenced": [f for f in fields if f not in collector.referenced],
            "epistemic_rendered": epistemic_rendered,
            "epistemic_subkeys_unnamed": (
                [k for k in _EPISTEMIC_SUBKEYS if not _mentions(node, k)]
                if epistemic_rendered else []
            ),
        })
    return findings, None


def audit_file(path: Path) -> List[Dict[str, object]]:
    """Return the structured findings for every text builder in one module.

    The programmatic entry point, used by the ``render_boundary_notice`` hook so the
    column diff arrives when a brief file is opened rather than when someone remembers to
    ask for it.

    Args:
        path: A python file to audit.

    Returns:
        ``[{"function", "lineno", "findings", "reason"}]`` — empty when the module builds
        no model-facing text. Never raises: an unparseable file yields ``[]``.
    """
    try:
        scan = sorted(_SRC.glob("*.py")) + sorted(_SRC.glob("crews/**/*.py"))
        scan = [p for p in scan if "deliverables" not in p.parts and "tests" not in p.parts]
        schemas = collect_record_schemas(scan)
        builders = find_text_builders([path])
    except (OSError, ValueError):
        return []

    out: List[Dict[str, object]] = []
    for _module, func, node in builders:
        findings, reason = analyze(node, schemas)
        out.append({
            "function": func, "lineno": node.lineno,
            "findings": findings, "reason": reason,
        })
    return out


def report(
    module: str,
    func: str,
    node: ast.FunctionDef,
    schemas: Dict[str, Dict[str, List[str]]],
    top_only: bool = True,
) -> Optional[str]:
    """Print the source-vs-rendered table for one text builder.

    Args:
        module: Dotted module path.
        func: Function name.
        node: Its parsed AST node.
        schemas: Record schemas to match against.
        top_only: Report only the best-matching record type.

    Returns:
        ``None`` when a table was printed, else the reason no diff was possible. The two
        reasons are different findings, not one: a function reading no fields at all was
        handed values its CALLER already projected (so the boundary to audit is upstream),
        while a function reading fields that match no declared class is building text from
        an ad-hoc dict — a shape nothing declares, so no diff of any kind is available to
        anyone.
    """
    findings, reason = analyze(node, schemas)
    if reason:
        return reason

    print(f"\n{'=' * 78}\n{module}:{func}  (line {node.lineno})\n{'=' * 78}")
    for finding in (findings[:1] if top_only else findings):
        rendered = set(finding["rendered"])          # type: ignore[arg-type]
        referenced = set(finding["referenced_not_rendered"])  # type: ignore[arg-type]

        print(f"\n  source record: {finding['record']}  "
              f"({finding['overlap']} field names in common)")
        print(f"  {'field':<38} {'in the emitted text?'}")
        print(f"  {'-' * 38} {'-' * 28}")
        for field in finding["fields"]:  # type: ignore[union-attr]
            if field in rendered:
                mark = "rendered"
            elif field in referenced:
                mark = "referenced, not rendered"
            else:
                mark = "not referenced"
            print(f"  {field:<38} {mark}")
        print(f"\n  counts: {len(rendered)} rendered · {len(referenced)} "
              f"referenced-not-rendered · {len(finding['not_referenced'])} not referenced")  # type: ignore[arg-type]

        epistemic = finding["epistemic_rendered"]
        unnamed = finding["epistemic_subkeys_unnamed"]
        if epistemic and unnamed:
            print(f"\n  {len(epistemic)} block(s) are rendered as a BARE NUMBER: "  # type: ignore[arg-type]
                  f"{', '.join(epistemic[:4])}"  # type: ignore[index]
                  f"{', …' if len(epistemic) > 4 else ''}")  # type: ignore[arg-type]
            print(f"    The `{'` and `'.join(unnamed)}` text stored inside each block — the "  # type: ignore[arg-type]
                  f"sentence saying what the number describes — is never named in this")
            print(f"    function, so it cannot reach the reader. They get the figure "
                  f"without the thing it is about.")

        upstream = finding["upstream"]
        if upstream:
            print(f"\n  NOT AN ALL-CLEAR — {finding['record']} is itself a narrowed record.")
            print("  A faithful render of a narrowed record still starves its reader, and that "
                  "drop is invisible")
            print("  at THIS boundary because nothing is left here to diff. Records holding "
                  "columns it has no room for:")
            for source, only in upstream[:3]:  # type: ignore[index]
                print(f"    {source:<28} {len(only):>2} column(s): "
                      f"{', '.join(only[:5])}{', …' if len(only) > 5 else ''}")
            print(f"  Check with: python tools/projection_audit.py --source "
                  f"<{'|'.join(s for s, _ in upstream[:3])}>")  # type: ignore[index]
    return None


def _target_filter(targets: Sequence[str], module: str, func: str) -> bool:
    """Return whether a function matches any ``module:function`` selector."""
    for target in targets:
        want_mod, _, want_func = target.partition(":")
        if want_mod and not module.endswith(want_mod):
            continue
        if want_func and want_func != func:
            continue
        return True
    return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns 0 always — this tool reports, it never passes or fails."""
    parser = argparse.ArgumentParser(
        description="Print what a record holds beside what its brief prints (channel 4).")
    parser.add_argument("--target", action="append", default=[],
                        help="Audit only 'module:function' (repeatable). Bypasses the name rule.")
    parser.add_argument("--all-matches", action="store_true",
                        help="Report every matching record type, not just the best.")
    parser.add_argument("--show-skipped", action="store_true",
                        help="List qualifying functions no record type matched.")
    args = parser.parse_args(argv)

    scan = sorted(_SRC.glob("*.py")) + sorted(_SRC.glob("crews/**/*.py"))
    scan = [p for p in scan if "deliverables" not in p.parts and "tests" not in p.parts]

    # Schemas come from every scanned module, not just db_models: a brief's source record is
    # as often a verdict/finding Pydantic class declared beside the gate that builds it
    # (IdentityFinding, CoverageVerdict) as it is a persisted vault table.
    schemas = collect_record_schemas(scan)
    builders = find_text_builders(scan)

    if args.target:
        builders = [b for b in builders if _target_filter(args.target, b[0], b[1])]
        if not builders:
            # A --target may name a function the name rule excludes; re-scan without it.
            for path in scan:
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
                except (SyntaxError, OSError):
                    continue
                module = str(path.relative_to(_SRC)).replace("/", ".")[:-3]
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and _target_filter(
                            args.target, module, node.name):
                        builders.append((module, node.name, node))

    print("render_audit — channel 4 (briefs built in python)")
    print(f"  selection rule : name starts with {list(_NAME_PREFIXES)} or contains "
          f"{list(_NAME_CONTAINS)}, and the body contains an f-string")
    print(f"  record schemas : {len(schemas)} classes from db_models.py + crews/*/models.py")
    print(f"  record matched : >= {_MIN_OVERLAP} field names in common with the function")
    print(f"  columns hidden : {sorted(_HOUSEKEEPING)} (row identity / capture metadata)")
    print(f"  functions found: {len(builders)}")
    print("  NOT covered    : tasks.yaml, schema field descriptions, tool return strings")
    print("\n  This tool reports what the code does. It does not rule on whether any row is a")
    print("  defect — some fields are withheld from makers deliberately.")

    skipped: List[Tuple[str, str]] = []
    for module, func, node in builders:
        reason = report(module, func, node, schemas, top_only=not args.all_matches)
        if reason:
            skipped.append((f"{module}:{func}", reason))

    if skipped:
        print(f"\n{'=' * 78}\nno diff available ({len(skipped)}) — these build model-facing "
              f"text this tool\ncannot put a source column beside:\n{'=' * 78}")
        for item, reason in sorted(skipped, key=lambda t: (t[1], t[0])):
            print(f"  {item:<52} {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
