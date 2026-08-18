#!/usr/bin/env bash
#
# blind-triage.sh — run the four-phase blind-triage protocol from the terminal.
#
# WHAT THIS REPLACES
# ------------------
# `.claude/skills/blind-triage/SKILL.md` splits triage into four phases separated by a CONTEXT
# CLEAR, because the whole point is that Phase 2 must not be able to see the report Phase 0
# quarantined. In the chat UI that clear is manual: you type /clear, then copy-paste the handoff
# packet into a fresh session. Four times. Per bug.
#
# In the CLI the clear is FREE. Every `claude -p` invocation is its own process with its own
# context window, so a new process IS a cleared session — a stronger guarantee than /clear, because
# nothing can leak even by accident. This script runs one process per phase and carries exactly one
# artifact across each boundary: the handoff packet the previous phase wrote to disk.
#
# WHAT IT DELIBERATELY DOES NOT REPLACE
# -------------------------------------
# The human stop line. The protocol's value is that YOU inspect each packet before it becomes the
# next phase's only input — bouncing a packet that names a cause in Phase 1, or one with a blank
# ORPHAN OBSERVATIONS field. So the script pauses at every boundary and shows you what to look for.
# `--auto` removes the pauses; it also removes the reason the protocol works. Use it knowingly.
#
# PLAN BY DEFAULT — the one place this driver departs from SKILL.md
# -----------------------------------------------------------------
# SKILL.md's Phase 4 is "Fix": it opens files and writes code. This driver runs Phase 4 in PLAN
# mode instead, and you opt into authoring with `--fix`. Nothing about the skill changed — the
# deviation lives here, in the driver, and only in what Phase 4 is allowed to do with its findings.
#
# The plan is not a summary. It is exactly the work SKILL.md makes mandatory BEFORE any file may be
# opened — the drop ledger, the REQUEST/RESPONSE classification of every survivor, the fix kind, the
# measured size against the budget, the maker-obligation quote, the killing question answered
# unprompted — with the editing left out. So `--fix` is not a second diagnosis; it is the same
# phase, permitted to type.
#
# SAFETY
# ------
# * Git writes are denied to every phase (CLI deny-list + the repo's own git_write_guard hook).
#   Even in --fix mode the change lands UNCOMMITTED in your working tree, per CLAUDE.md.
# * In plan mode NO phase can edit source: Edit is absent from every toolset, phases 1-4.
# * The case dir lives OUTSIDE the repo (~/.claude-triage by default) so a later phase cannot read
#   the sealed report, an earlier prompt, or an earlier transcript. Only packets/ is granted back.
#   See the case-directory block below for the measurement that forced this.
# * PIPELINE_OFFLINE=1 comes from .claude/settings.json and is inherited by every phase, so the
#   offline guard stays armed exactly as it is in the chat UI. No phase can spend on Gemini or other paid APIs.
#
# USAGE
#   scripts/triage/blind-triage.sh "ECR-114: pinmux brief drops the peripheral column"
#   scripts/triage/blind-triage.sh -f docs/verification_findings.csv
#   scripts/triage/blind-triage.sh --fix "ECR-114: …"          # author the change, don't just plan
#   scripts/triage/blind-triage.sh --case .triage/…_ecr-114 --phase 4 --fix   # approve a plan
#   scripts/triage/blind-triage.sh --help
#
set -Eeuo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Locations
# ─────────────────────────────────────────────────────────────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
STREAM_FILTER="$HERE/_stream.py"
SKILL_FILE="$REPO_ROOT/.claude/skills/blind-triage/SKILL.md"

# ─────────────────────────────────────────────────────────────────────────────
# Defaults (every one overridable by a flag or an env var)
# ─────────────────────────────────────────────────────────────────────────────
MODEL="${TRIAGE_MODEL:-claude-opus-5}" # phases 0-3: measurement and reasoning.
                                       #   Pinned to a full id, not the `opus` alias: the alias
                                       #   resolves to whatever the CLI calls current (on 2.1.197
                                       #   it came back as claude-opus-4-8).
FIX_MODEL="${TRIAGE_FIX_MODEL:-}"      # phase 4: authoring. Empty => same as MODEL.
                                       #   CLAUDE.md's split says Fable authors, Opus does QA.
                                       #   Set TRIAGE_FIX_MODEL=fable to follow it literally.
PERM_MODE="${TRIAGE_PERMISSION_MODE:-acceptEdits}"
CASE_DIR=""
START_PHASE=1
STOP_AFTER=4
AUTO=0
DRY_RUN=0
REPORT_TEXT=""
REPORT_FILE=""
MODE="${TRIAGE_PHASE4_MODE:-plan}"     # plan | fix. See "PLAN BY DEFAULT" above.

# Git stays the human's, in every phase. This is the CLI-level deny; .claude/hooks/git_write_guard.py
# is the second layer and catches the compound form (`cd src && git commit`) that prefix matching
# cannot see.
GIT_DENY=(
  "Bash(git add:*)"   "Bash(git commit:*)"  "Bash(git checkout:*)" "Bash(git switch:*)"
  "Bash(git merge:*)" "Bash(git branch:*)"  "Bash(git rebase:*)"   "Bash(git reset:*)"
  "Bash(git push:*)"  "Bash(git pull:*)"    "Bash(git stash:*)"    "Bash(git tag:*)"
  "Bash(git restore:*)" "Bash(git cherry-pick:*)" "Bash(git revert:*)" "Bash(git clean:*)"
)

# Phases 1-3 measure; they have no business editing source. Write survives only because each phase
# has to write its handoff packet. Phase 4 gets TOOLS_MEASURE too unless --fix was passed, so
# "plan only" is a property of the toolset rather than a promise in a prompt.
TOOLS_MEASURE="Bash,Read,Grep,Glob,Write,Skill,TodoWrite"
TOOLS_FIX="Bash,Read,Grep,Glob,Write,Edit,Skill,TodoWrite"

# ─────────────────────────────────────────────────────────────────────────────
# Terminal helpers
# ─────────────────────────────────────────────────────────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  B=$'\033[1m'; DIM=$'\033[2m'; YEL=$'\033[33m'; CYA=$'\033[36m'; RED=$'\033[31m'; N=$'\033[0m'
else
  B=""; DIM=""; YEL=""; CYA=""; RED=""; N=""
fi

say()  { printf '%s\n' "$*"; }
rule() { printf '%s\n' "${DIM}────────────────────────────────────────────────────────────────────────${N}"; }
die()  { printf '%s\n' "${RED}error:${N} $*" >&2; exit 1; }

usage() {
  # The header comment IS the help text — print it up to the first line of real code, so the two
  # can never drift apart.
  sed -n '2,/^set -/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
  exit 0
}

# ─────────────────────────────────────────────────────────────────────────────
# Arguments
# ─────────────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--file)        REPORT_FILE="${2:?--file needs a path}"; shift 2 ;;
    -m|--model)       MODEL="${2:?--model needs an alias}"; shift 2 ;;
    --fix-model)      FIX_MODEL="${2:?--fix-model needs an alias}"; shift 2 ;;
    --case)           CASE_DIR="${2:?--case needs a directory}"; shift 2 ;;
    --phase)          START_PHASE="${2:?--phase needs 1-4}"; shift 2 ;;
    --stop-after)     STOP_AFTER="${2:?--stop-after needs 1-4}"; shift 2 ;;
    --permission-mode) PERM_MODE="${2:?}"; shift 2 ;;
    --fix)            MODE="fix"; shift ;;
    --plan)           MODE="plan"; shift ;;
    --auto)           AUTO=1; shift ;;
    --dry-run)        DRY_RUN=1; shift ;;
    -h|--help)        usage ;;
    -*)               die "unknown option: $1  (try --help)" ;;
    *)                REPORT_TEXT="${REPORT_TEXT}${REPORT_TEXT:+$'\n'}$1"; shift ;;
  esac
done

[[ -x "$(command -v claude)" ]] || die "the 'claude' CLI is not on PATH."
[[ -f "$SKILL_FILE" ]] || die "blind-triage skill not found at $SKILL_FILE"
(( START_PHASE >= 1 && START_PHASE <= 4 )) || die "--phase must be 1-4"
(( STOP_AFTER >= START_PHASE && STOP_AFTER <= 4 )) || die "--stop-after must be >= --phase and <= 4"
[[ "$MODE" == "plan" || "$MODE" == "fix" ]] || die "mode must be plan or fix (--plan / --fix)"
[[ -n "$FIX_MODEL" ]] || FIX_MODEL="$MODEL"

# A report is required to START at phase 1; resuming later needs a case dir with packets in it.
if (( START_PHASE == 1 )); then
  if [[ -z "$REPORT_TEXT" && -z "$REPORT_FILE" && ! -t 0 ]]; then
    REPORT_TEXT="$(cat)"            # allows:  cat finding.txt | blind-triage.sh
  fi
  [[ -n "$REPORT_TEXT" || -n "$REPORT_FILE" ]] || die "no report given. Pass text, -f <file>, or pipe it in."
else
  [[ -n "$CASE_DIR" ]] || die "--phase >1 needs --case <dir> so it can read the previous packet."
fi

# ─────────────────────────────────────────────────────────────────────────────
# The case directory — one per bug, holds every prompt, log and packet
#
# IT LIVES OUTSIDE THE REPO, AND THAT IS THE BLINDING.
# Observed: a headless phase with the measure toolset read a file under the repo's
# .triage/ without any prompt, and was DENIED on the identical read one directory outside the
# workspace. So "the report is sealed" is worth only as much as the filesystem makes it worth:
# with the case dir in-repo, Phase 2 could `cat report.original.txt` and un-blind itself, or read
# Phase 1's transcript and inherit the reasoning the /clear was supposed to drop.
#
# Out here, none of it is reachable. Only $CASE_DIR/packets is granted back (--add-dir, in
# run_claude), because the packets ARE the designed handoff — they are blinded by construction.
# Everything that carries the poison — report.original.txt, prompts/, logs/ — stays unreadable.
#
# TRIAGE_HOME moves it. Point it inside the repo and you get the leak back; that is your call.
# ─────────────────────────────────────────────────────────────────────────────
if [[ -z "$CASE_DIR" ]]; then
  slug="$(printf '%s' "${REPORT_TEXT:-$REPORT_FILE}" | tr '[:upper:]' '[:lower:]' \
          | tr -cs 'a-z0-9' '-' | cut -c1-40 | sed 's/-*$//')"
  CASE_DIR="${TRIAGE_HOME:-$HOME/.claude-triage}/$(date +%Y%m%d_%H%M%S)_${slug:-case}"
fi
mkdir -p "$CASE_DIR"/{prompts,logs,packets,scratch}
CASE_DIR="$(cd "$CASE_DIR" && pwd)"

# The original report is stored ONCE, here, and never re-fed to a later phase. Phase 0 blinds it;
# re-pasting it downstream is the documented way to re-poison the protocol.
if (( START_PHASE == 1 )); then
  if [[ -n "$REPORT_FILE" ]]; then
    [[ -f "$REPORT_FILE" ]] || die "no such file: $REPORT_FILE"
    REPORT_FILE="$(cd "$(dirname "$REPORT_FILE")" && pwd)/$(basename "$REPORT_FILE")"
  fi
  printf '%s\n' "${REPORT_TEXT:-(from file: $REPORT_FILE)}" > "$CASE_DIR/report.original.txt"
fi

# Every path above is now absolute, so it is safe to move. And we MUST move: `claude` treats its
# working directory as the workspace — that is what decides whether CLAUDE.md loads, whether the
# repo's hooks fire, and whether `cd src && python tools/render_audit.py` resolves. Run this script
# from your home directory without this line and the phases would triage an empty folder.
cd "$REPO_ROOT"

# ─────────────────────────────────────────────────────────────────────────────
# Packet extraction fallback
#
# Each phase is told to Write its packet straight to disk — the reliable path. If it didn't, we
# salvage the packet from the transcript instead, between the two literal marker lines. Losing a
# finished phase to a missing file would be an expensive way to fail.
# ─────────────────────────────────────────────────────────────────────────────
extract_packet_from_log() {
  local log="$1" out="$2"
  python3 - "$log" "$out" <<'PY'
import json, sys
log_path, out_path = sys.argv[1], sys.argv[2]
chunks = []
with open(log_path, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []) or []:
                if block.get("type") == "text":
                    chunks.append(block.get("text", ""))
        elif ev.get("type") == "result" and isinstance(ev.get("result"), str):
            chunks.append(ev["result"])
text = "\n".join(chunks)
start, end = "===BEGIN PACKET===", "===END PACKET==="
if start in text and end in text:
    body = text.split(start, 1)[1].split(end, 1)[0].strip()
    if body:
        open(out_path, "w", encoding="utf-8").write(body + "\n")
        sys.exit(0)
sys.exit(1)
PY
}

# ─────────────────────────────────────────────────────────────────────────────
# One phase = one fresh `claude -p` process
# ─────────────────────────────────────────────────────────────────────────────
run_claude() {
  local phase="$1" prompt_file="$2" model="$3" tools="$4" sys_prompt="$5"
  local log="$CASE_DIR/logs/phase${phase}.jsonl"

  # Keep prior attempts (a bounce re-runs the same phase) instead of overwriting the evidence.
  [[ -f "$log" ]] && mv "$log" "${log%.jsonl}.$(date +%H%M%S).jsonl"

  if (( DRY_RUN )); then
    say "${DIM}[dry-run] would run phase $phase with model=$model tools=$tools${N}"
    say "${DIM}[dry-run] prompt: $prompt_file${N}"
    return 0
  fi

  # Notes on the invocation, each one paid for by a failed experiment:
  #   < /dev/null       the prompt is an argument; without this the CLI waits 3s for stdin that
  #                     never comes, and warns about it.
  #   --allowed-tools   acceptEdits does NOT auto-approve Bash. It waves through commands the CLI
  #                     classifies as safe (`echo`, `git status`) and PROMPTS for the rest — and a
  #                     prompt with no human is a denial. Observed: every
  #                     `python tools/…_audit.py` call in Phase 1 was refused, so the phase spent
  #                     its turns reading settings files trying to work out why. Naming the tools
  #                     here allows them outright; the deny-list below still wins over it.
  #   --add-dir         grants exactly TWO directories back: packets/ (the phase's deliverable)
  #                     and scratch/ (working files, since /tmp is outside the workspace and
  #                     blocked). The case dir's PARENT is deliberately not granted, so
  #                     report.original.txt, prompts/ and logs/ stay unreadable. Do not widen this
  #                     to "$CASE_DIR"; that hands Phase 2 the sealed report.
  #   2>&1              folds the CLI's own warnings (e.g. an untrusted workspace) into the stream,
  #                     so they reach the log and the human instead of vanishing.
  set +e
  claude -p "$(cat "$prompt_file")" \
    --model "$model" \
    --output-format stream-json --verbose \
    --permission-mode "$PERM_MODE" \
    --tools "$tools" \
    --allowed-tools "Bash" "Read" "Grep" "Glob" "Write" \
    --disallowed-tools "${GIT_DENY[@]}" \
    --add-dir "$CASE_DIR/packets" "$CASE_DIR/scratch" \
    --append-system-prompt "$sys_prompt" \
    < /dev/null 2>&1 | tee "$log" | python3 "$STREAM_FILTER"
  local status=${PIPESTATUS[0]}
  set -e
  return "$status"
}

# Where a phase's deliverable lands. Phase 4 in plan mode produces a plan rather than a handoff
# packet, and it is named as such — a reviewer should never have to guess which file is the ask.
packet_path_for() {
  local phase="$1"
  if (( phase == 4 )); then
    printf '%s' "$CASE_DIR/packets/phase4-plan.md"
  else
    printf '%s' "$CASE_DIR/packets/phase${phase}.md"
  fi
}

# Runs a phase, then makes sure its deliverable exists on disk.
run_phase() {
  local phase="$1" prompt_file="$2" model="$3" tools="$4" sys_prompt="$5"
  local packet; packet="$(packet_path_for "$phase")"

  local label="PHASE $phase"
  (( phase == 4 )) && label="PHASE 4 (${MODE})"
  rule
  say "${B}${label}${N}  ${DIM}· model=$model · fresh context (this is the /clear)${N}"
  rule

  run_claude "$phase" "$prompt_file" "$model" "$tools" "$sys_prompt" \
    || die "phase $phase: claude exited non-zero. Transcript: $CASE_DIR/logs/phase${phase}.jsonl"

  (( DRY_RUN )) && return 0
  # In --fix mode phase 4 ends in a working-tree change, not a file we can check for.
  [[ "$phase" == "4" && "$MODE" == "fix" ]] && return 0

  if [[ ! -s "$packet" ]]; then
    local resume_hint=""
    (( phase < 4 )) && resume_hint="
       …then resume with:  $0 --case '$CASE_DIR' --phase $((phase + 1))"
    extract_packet_from_log "$CASE_DIR/logs/phase${phase}.jsonl" "$packet" \
      || die "phase $phase wrote nothing to $packet.
       Read the transcript ($CASE_DIR/logs/phase${phase}.jsonl) and salvage it by hand into that
       path.${resume_hint}"
    say "${YEL}note:${N} recovered from the transcript rather than written directly."
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# The stop line — the part that is deliberately NOT automated
# ─────────────────────────────────────────────────────────────────────────────
stop_line() {
  local phase="$1" watch="$2"
  local packet; packet="$(packet_path_for "$phase")"

  say ""
  rule
  say "${B}═══ PHASE $phase COMPLETE ($phase of 4 done) ═══${N}"
  say "packet: ${CYA}${packet}${N}"
  say ""
  say "${YEL}${watch}${N}"
  rule

  # THE GLANCE CHECK, mechanised where it can be. These are cheap string tests, not judgement —
  # they catch the two failure shapes the skill says have actually cost runs.
  if (( phase >= 1 && phase <= 3 )) && [[ -f "$packet" ]]; then
    grep -qi 'ORPHAN OBSERVATIONS' "$packet" \
      || say "${RED}glance check:${N} no ORPHAN OBSERVATIONS field in this packet. The skill says bounce it."
    grep -qi 'BOUNDARY DROPS' "$packet" \
      || say "${RED}glance check:${N} no BOUNDARY DROPS field. Phase 4 cannot build a drop ledger without it."
  fi

  if (( AUTO )); then
    say "${DIM}--auto: continuing without review.${N}"
    return 0
  fi

  while true; do
    say ""
    printf '%s' "${B}[Enter]${N} read it, continue  ${B}[p]${N} print packet  ${B}[e]${N} edit packet  ${B}[b]${N} bounce & re-run  ${B}[s]${N} stop here > "
    local key; read -r key < /dev/tty || key="s"
    case "${key,,}" in
      "")  return 0 ;;
      p)   rule; cat "$packet"; rule ;;
      e)   "${EDITOR:-nano}" "$packet" < /dev/tty > /dev/tty 2>&1 || true ;;
      b)   return 2 ;;
      s)   say "stopped. Resume with:  $0 --case '$CASE_DIR' --phase $((phase + 1))"; exit 0 ;;
      *)   say "${DIM}(unrecognised — Enter, p, e, b or s)${N}" ;;
    esac
  done
}

# A bounce is the skill's own instruction ("bounce it and say ...") made executable: same phase,
# same input, plus your objection.
bounce_note() {
  say ""
  say "${B}Your objection${N} — one line, handed to the phase verbatim (it re-runs from scratch):"
  printf '> '
  local note; read -r note < /dev/tty || note=""
  printf '%s' "$note"
}

# ─────────────────────────────────────────────────────────────────────────────
# Prompt bodies
#
# Every phase prompt opens with the /blind-triage slash command, so the CLI loads the skill itself —
# the SKILL.md file stays the single source of truth for the protocol and this script never
# paraphrases it. What the script adds is only what the skill cannot know: that there is no human in
# the loop, where the packet must be written, and where the phase must stop.
# ─────────────────────────────────────────────────────────────────────────────
headless_preamble() {
  cat <<EOF
You are running HEADLESS, driven by scripts/triage/blind-triage.sh. Facts about this session:

- There is NO human here to answer a question mid-phase. If you would ask one, write it into the
  packet's OPEN QUESTIONS field and carry on with what you can measure.
- Do NOT run /clear and do NOT ask anyone to. Each phase is a separate process with a fresh context
  window; the driver already gave you the clean session the protocol calls for.
- You may not perform ANY git write (add, commit, checkout, branch, merge, push, stash). They are
  denied at the CLI. The human does those.
- DO NOT WRITE, UPDATE OR DELETE AN AUTO-MEMORY, and do not ask to. Memories load automatically
  into EVERY later phase's context — it is the one channel the packet discipline does not cover, so
  a memory written now would un-blind a later phase by a route no file permission can block.
  Anything worth carrying forward goes in the packet, where the human can read it and bounce it.
  Reading the memories already there is fine; they predate this case.
- /tmp IS OUTSIDE THE WORKSPACE and every write to it is blocked, including shell redirection
  (\`> /tmp/out.txt\`). For a scratch file use this directory, which is granted to you:
    $CASE_DIR/scratch
  Many of this repo's tools also take an --out flag, which is cheaper than redirecting.
- Execute ONLY the phase named below. Do not continue into the next one.
EOF
}

packet_contract() {
  local path="$1" noun="${2:-paste-ready handoff packet}"
  cat <<EOF

DELIVERABLE — BOTH of these, or the driver cannot carry your work forward:
  1. Print your normal phase report to stdout, exactly as the skill specifies.
  2. Write the $noun — and NOTHING ELSE in the file — to this exact path,
     using the Write tool:
       $path
     Then repeat it in your final message between two literal marker lines:
       ===BEGIN PACKET===
       <the packet>
       ===END PACKET===
     (The file is what gets used; the markers are the salvage path if the write fails.)
EOF
}

build_phase1_prompt() {
  local out="$CASE_DIR/prompts/phase1.txt"
  {
    echo "/blind-triage"
    echo
    headless_preamble
    echo
    echo "EXECUTE PHASE 0 (Quarantine) AND PHASE 1 (Evidence). Stop at the Phase 1 stop line."
    echo "Phase 1's hard ban is the whole point: no cause, no suspect module, no 'intersection',"
    echo "no fix kind — not hedged, not parenthetically, not in passing."
    echo
    echo "THE REPORT (unblinded — quarantine it in Phase 0, then treat it as SEALED):"
    echo "<<<REPORT"
    if [[ -n "$REPORT_FILE" ]]; then
      # Small files are inlined so the blinding happens on the real words. Big ones are handed over
      # as a path — reading it is the model's first act either way.
      if [[ "$(stat -c%s "$REPORT_FILE")" -le 8192 ]]; then
        cat "$REPORT_FILE"
      else
        echo "The report is the file: $REPORT_FILE"
        echo "Read it first, then quarantine it."
      fi
      [[ -n "$REPORT_TEXT" ]] && { echo; printf '%s\n' "$REPORT_TEXT"; }
    else
      printf '%s\n' "$REPORT_TEXT"
    fi
    echo "REPORT>>>"
    packet_contract "$CASE_DIR/packets/phase1.md"
  } > "$out"
  printf '%s' "$out"
}

build_carry_prompt() {
  # Phases 2-4 receive ONE artifact: the previous phase's packet. Nothing else crosses.
  local phase="$1" instruction="$2" packet_path="$3"
  local prev=$((phase - 1))
  local out="$CASE_DIR/prompts/phase${phase}.txt"
  [[ -s "$CASE_DIR/packets/phase${prev}.md" ]] \
    || die "phase $phase needs $CASE_DIR/packets/phase${prev}.md and it is missing or empty."
  {
    echo "/blind-triage"
    echo
    headless_preamble
    echo
    printf '%s\n' "$instruction"
    echo
    echo "You have NO prior context and you must not go looking for the original report — it was"
    echo "sealed in Phase 0. This packet is your entire inheritance:"
    echo
    echo "<<<PACKET"
    cat "$CASE_DIR/packets/phase${prev}.md"
    echo "PACKET>>>"
    if [[ -n "$packet_path" ]]; then
      packet_contract "$packet_path"
    fi
  } > "$out"
  printf '%s' "$out"
}

# Phase 4 is the one phase whose deliverable depends on the mode, so it gets its own builder.
#
# The plan template invents nothing. Sections 1-3 and 5-7 are the artifacts SKILL.md already makes
# MANDATORY before any file may be opened — the drop ledger, the REQUEST/RESPONSE classification,
# the fix kind, the measured size, the maker obligation, the killing question. Plan mode is that
# work with the typing withheld, which is why `--fix` afterwards is not a second diagnosis.
build_phase4_prompt() {
  local out="$CASE_DIR/prompts/phase4.txt"
  local plan_file="$CASE_DIR/packets/phase4-plan.md"
  [[ -s "$CASE_DIR/packets/phase3.md" ]] \
    || die "phase 4 needs $CASE_DIR/packets/phase3.md and it is missing or empty."
  {
    echo "/blind-triage"
    echo
    headless_preamble
    echo
    if [[ "$MODE" == "plan" ]]; then
      cat <<'PLAN'
EXECUTE PHASE 4 IN PLAN MODE — produce the plan, write NO code.

You may read, grep and run measurement commands. You may not edit a source file: Edit is absent
from your toolset, so this is a fact about the session and not a request. Everything CLAUDE.md
says about Phase 4 still binds — one deadlock, the size budget, fix kinds (a)/(b)/(c) only, a new
gate is not a fix — because sections 1-3 and 5-7 below are exactly the work the skill already
requires BEFORE any file may be opened. Do that measuring in full. Just stop before the diff.

THE PLAN — write these sections, in this order:

1. DROP LEDGER. One line per drop in the packet's BOUNDARY DROPS field, upstream -> downstream:
     <boundary> · <field or value that did not cross> · would fixing THIS ALONE have prevented
     the symptom?  yes | no | unproven
   The fix goes to the TOPMOST yes — not the cheapest, not the one nearest the symptom, not the
   one whose test you can already picture. `no` on the near drop is a verdict, not a footnote.
   `unproven` never breaks a tie. If the packet carries no BOUNDARY DROPS field, that is a Phase 1
   OMISSION and not an empty ledger: re-run the boundary audits and rebuild it before ranking.

2. SURVIVOR CLASSIFICATION. For every account Phase 3 left alive, one line:
     <account> — first appearance: REQUEST | RESPONSE | not established
   A REQUEST appearance routes the account upstream to (a)/(b)/(c), and the render/projection
   audits against the module that BUILT that request must actually be run — a paragraph explaining
   why you find another account more compelling does not discharge it.

3. FIX KIND — (a) give a consumer data it already lacks · (b) delete a demand nobody can satisfy ·
   (c) collapse duplicate implementations. (d) add-or-tighten-a-check is NOT available. If you
   find yourself arguing that your new check counts as an (a), stop and say so: that argument is
   itself the diagnosis.

4. THE CHANGE, IN WORDS. Exact files and functions, what changes in each, and a concrete
   before/after of the value that is wrong. Enough that a tired reader can picture the diff
   without you having written it. No code blocks of the proposed implementation.

5. SIZE, MEASURED. Estimated changed lines and file count against the budget (<=150 lines across
   <=3 files), plus HOW you arrived at the number. An asserted cost is not a measurement and has
   been wrong in this repo before. If it genuinely exceeds, say so in three sentences — that is a
   stop for a ruling, never a licence to substitute a smaller downstream fix.

6. SYMMETRY. If the change touches a gate, brief or grader: the VERBATIM maker sentence you would
   quote as MAKER_OBLIGATION, and the test_<module>_is_winnable you would add. If you cannot find
   a maker sentence to quote, say so plainly — the gate is one-sided, and that is the whole bug.

7. THE KILLING QUESTION, answered unprompted: "What single result would have proved this wrong,
   and did you run it?" Name the result, and say whether you ran it.

8. CHECK THIS FIRST IF YOU DOUBT ME. The single cheapest command the human can run to falsify the
   plan before authorising it.

9. WHAT THIS PLAN DOES NOT COVER. Anything you set aside, and why. NONE is a claim, not a default.
PLAN
    else
      cat <<'FIXM'
EXECUTE PHASE 4 — AUTHOR THE FIX. Everything in CLAUDE.md governs from here: one deadlock, the
size budget (<=150 changed lines across <=3 files), fix kinds (a)/(b)/(c) only, maker/checker
symmetry, the trailers, the offline testing protocol.

Write the DROP LEDGER and the REQUEST/RESPONSE classification of every survivor BEFORE you open
any file to edit, and fix the topmost `yes`. Answer the killing question unprompted — "What single
result would have proved this wrong, and did you run it?" — before presenting anything.

Author the change in the working tree and STOP. Do not commit it; git writes are denied.
FIXM
      if [[ -s "$plan_file" ]]; then
        echo
        echo "An APPROVED PLAN for this case already exists. The human has read it and asked for it"
        echo "to be authored, so implement THAT — do not re-derive a different one. If your own"
        echo "measurements contradict it, STOP and say which line is wrong rather than quietly"
        echo "shipping something else."
        echo
        echo "<<<APPROVED_PLAN"
        cat "$plan_file"
        echo "APPROVED_PLAN>>>"
      fi
    fi
    echo
    echo "You have NO prior context and you must not go looking for the original report — it was"
    echo "sealed in Phase 0. This packet is your inheritance:"
    echo
    echo "<<<PACKET"
    cat "$CASE_DIR/packets/phase3.md"
    echo "PACKET>>>"
    [[ "$MODE" == "plan" ]] && packet_contract "$plan_file" "PLAN — sections 1 to 9 above, in order"
  } > "$out"
  printf '%s' "$out"
}

# ─────────────────────────────────────────────────────────────────────────────
# Per-phase system prompts. A system prompt outranks a user prompt, so the one rule each phase
# most often breaks goes here rather than in the body.
# ─────────────────────────────────────────────────────────────────────────────
SYS_P1="You are Phase 1 of blind-triage. HARD BAN: you may not name a cause, a suspect module, an intersection, or a fix kind — hedged or otherwise. Evidence only. Every list a tool returns gets a per-row verdict in writing. Every escalation a tool names gets RUN in this phase. Anything you set aside goes in ORPHAN OBSERVATIONS verbatim; NONE is a claim, not a default."
SYS_P2="You are Phase 2 of blind-triage. Produce 2-3 RIVAL accounts and refuse to rank them. At least one must be 'a consumer is being starved of a field that exists upstream'. A confirming test does not count — only the single test that would KILL each account. Carry every orphan observation and boundary drop forward verbatim."
SYS_P3="You are Phase 3 of blind-triage. Build every fixture by CALLING THE PRODUCTION CODE — no SQL, no vault dump, no hand-written dict standing in for real data. Report survivors and corpses, nothing else. If ZERO accounts survive the phase is NOT over: close the holes the packet names and re-read the boundaries no account sent you to."
SYS_P4_FIX="You are Phase 4 of blind-triage. CLAUDE.md governs from here: one deadlock, <=150 changed lines across <=3 files, fix kinds (a)/(b)/(c) only — a new gate is not a fix. Write the DROP LEDGER before you open any file to edit, and fix the topmost 'yes'. Answer unprompted: 'What single result would have proved this wrong, and did you run it?' You may edit files. You may NOT run any git command that writes."
SYS_P4_PLAN="You are Phase 4 of blind-triage, running in PLAN mode. You produce a plan and write NO code — Edit is not in your toolset, and a proposed implementation pasted into the plan is the same violation by another route. This is not a lighter Phase 4: the drop ledger, the REQUEST/RESPONSE classification of every survivor, the fix kind, the measured size and the maker-obligation quote are all still mandatory, because CLAUDE.md already requires them BEFORE any file may be opened. Rank drops upstream-first and recommend the topmost 'yes'. Answer unprompted: 'What single result would have proved this wrong, and did you run it?'"

# ─────────────────────────────────────────────────────────────────────────────
# Watch-for banners, lifted from the skill so the human gets them without opening SKILL.md
# ─────────────────────────────────────────────────────────────────────────────
WATCH_1="★ WATCH FOR IN PHASE 2: it must give you 2-3 RIVAL accounts and refuse to rank them.
  If it recommends one, or one arrives sounding obviously right — bounce it [b] and say
  \"give me the second account\". A favourite in Phase 2 is the old failure returning.
  Also check THIS packet: a sentence saying what the bug IS = contaminated. Bounce it."
WATCH_2="★ WATCH FOR IN PHASE 3: every fixture must be built by CALLING THE REAL CODE.
  If you see sqlite3, a SQL string, a vault dump or a hand-written dict standing in for
  real data — bounce it [b]. That is how a past 'fully validated' fix turned out inoperable."
WATCH_3="★ IF IT REPORTED ZERO SURVIVORS: there is no fix to carry into Phase 4, and the phase
  is not finished. Ask it two things before you accept it — bounce [b] with:
    \"Which holes did you name, and did you run them?\"
    \"Which boundary did none of the three accounts send you to, and did you look?\"
★ DUE IN PHASE 4, unprompted: \"What single result would have proved this wrong, and did
  you run it?\" and \"Is the drop you fixed the furthest upstream one?\""

# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
say ""
say "${B}blind-triage${N} ${DIM}· case $CASE_DIR${N}"
say "${DIM}phases ${START_PHASE}-${STOP_AFTER} · phase 4 = ${MODE} · model=$MODEL · perms=$PERM_MODE${N}"
if [[ "$MODE" == "plan" ]]; then
  say "${DIM}no phase can edit source in plan mode — Edit is absent from every toolset.${N}"
fi
say ""
say "${YEL}★ WATCH ME IN PHASE 1: if it names a cause — a suspect module, an \"intersection\", a fix"
say "  kind, even hedged — the protocol has collapsed. Bounce it [b] and it restarts clean.${N}"

phase="$START_PHASE"
while (( phase <= STOP_AFTER )); do
  case "$phase" in
    1) prompt="$(build_phase1_prompt)"; model="$MODEL"; tools="$TOOLS_MEASURE"; sys="$SYS_P1" ;;
    2) prompt="$(build_carry_prompt 2 "EXECUTE PHASE 2 (Competing accounts) ONLY." "$CASE_DIR/packets/phase2.md")"
       model="$MODEL"; tools="$TOOLS_MEASURE"; sys="$SYS_P2" ;;
    3) prompt="$(build_carry_prompt 3 "EXECUTE PHASE 3 (Discriminate) ONLY." "$CASE_DIR/packets/phase3.md")"
       model="$MODEL"; tools="$TOOLS_MEASURE"; sys="$SYS_P3" ;;
    4) prompt="$(build_phase4_prompt)"; model="$FIX_MODEL"
       if [[ "$MODE" == "fix" ]]; then tools="$TOOLS_FIX"; sys="$SYS_P4_FIX"
       else                            tools="$TOOLS_MEASURE"; sys="$SYS_P4_PLAN"; fi ;;
  esac

  run_phase "$phase" "$prompt" "$model" "$tools" "$sys"

  if (( phase == 4 || phase == STOP_AFTER )); then break; fi

  watch_var="WATCH_${phase}"
  set +e
  stop_line "$phase" "${!watch_var}"
  decision=$?
  set -e

  if (( decision == 2 )); then
    note="$(bounce_note)"
    if [[ -n "$note" ]]; then
      { echo; echo "HUMAN BOUNCE — the previous attempt at this phase was rejected. Objection:"; \
        printf '%s\n' "$note"; echo "Redo the phase addressing it. Do not defend the previous attempt."; } >> "$prompt"
    fi
    rm -f "$(packet_path_for "$phase")"
    continue                       # same phase, fresh process, your objection attached
  fi

  phase=$((phase + 1))
done

say ""
rule
if (( STOP_AFTER < 4 )); then
  say "${B}Stopped after phase $STOP_AFTER.${N}  Resume:  $0 --case '$CASE_DIR' --phase $((STOP_AFTER + 1))"
elif [[ "$MODE" == "plan" ]]; then
  say "${B}Phase 4 done — a PLAN, not a change.${N} Nothing in your working tree was touched."
  say ""
  say "plan: ${CYA}$(packet_path_for 4)${N}"
  say ""
  say "Read it, then either:"
  say "  ${CYA}$0 --case '$CASE_DIR' --phase 4 --fix${N}"
  say "      authors the approved plan — same case, fresh context, plan handed over"
  say "  ${CYA}$0 --case '$CASE_DIR' --phase 4${N}"
  say "      re-plans from the same Phase 3 evidence, if the plan was wrong"
  say ""
  say "${DIM}Section 8 of the plan names the cheapest command to falsify it. Run that first.${N}"
else
  say "${B}Phase 4 done.${N} The change is in your working tree, UNCOMMITTED — that part is yours."
  say ""
  say "Next, in this order:"
  say "  1. ${CYA}git diff${N}                       — read what it actually did"
  say "  2. ${CYA}cd src && pytest tests crews --ignore=tests/_scratch --ignore=tests/tests${N}"
  say "  3. commit it yourself (CLAUDE.md: the write is never delegated)"
fi
say "${DIM}case files: $CASE_DIR${N}"
rule
