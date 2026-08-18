#!/usr/bin/env bash
#
# fix-run.sh — the FIX RUN / WHY RUN protocol, from the terminal.
#
# The other half of the diagnostics pair. `blind-triage.sh` is for a bug that arrives ALREADY
# DIAGNOSED (a findings row, a ticket, a spreadsheet cell). This one is for the opposite input: a
# broken pipeline run and nothing else. It is a single `claude -p` call, because the fix-run
# protocol has no context-clear boundaries — the phases are what blind-triage adds.
#
# WHY / FIX
#   --why   (default)  stop at the diagnosis. No fix proposed. Read-only toolset.
#   --fix              diagnose, then author exactly one fix in the working tree.
#
# In both modes git writes are denied, so nothing is ever committed on your behalf.
#
# USAGE
#   scripts/triage/fix-run.sh                 # why did the newest run end?
#   scripts/triage/fix-run.sh --fix           # ...and fix the one deadlock
#   scripts/triage/fix-run.sh --why --model fable
#
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
STREAM_FILTER="$HERE/_stream.py"

MODE="why"
MODEL="${TRIAGE_MODEL:-opus}"
PERM_MODE="${TRIAGE_PERMISSION_MODE:-acceptEdits}"
EXTRA_NOTE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --why)   MODE="why"; shift ;;
    --fix)   MODE="fix"; shift ;;
    -m|--model) MODEL="${2:?--model needs an alias}"; shift 2 ;;
    --permission-mode) PERM_MODE="${2:?}"; shift 2 ;;
    # The header comment IS the help text — printed up to the first line of real code.
    -h|--help) sed -n '2,/^set -/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)      printf 'unknown option: %s\n' "$1" >&2; exit 1 ;;
    *)       EXTRA_NOTE="${EXTRA_NOTE}${EXTRA_NOTE:+ }$1"; shift ;;
  esac
done

command -v claude >/dev/null || { echo "the 'claude' CLI is not on PATH." >&2; exit 1; }

# `claude` treats its working directory as the workspace: it decides whether CLAUDE.md loads, whether
# the repo's hooks fire, and whether `cd src && python tools/run_forensics.py` resolves. So the
# script goes to the repo root itself, and you can call it from anywhere.
cd "$REPO_ROOT"

# Same deny-list as blind-triage.sh: the diagnosis and the authoring are delegated, the commit is not.
GIT_DENY=(
  "Bash(git add:*)"   "Bash(git commit:*)"  "Bash(git checkout:*)" "Bash(git switch:*)"
  "Bash(git merge:*)" "Bash(git branch:*)"  "Bash(git rebase:*)"   "Bash(git reset:*)"
  "Bash(git push:*)"  "Bash(git pull:*)"    "Bash(git stash:*)"    "Bash(git tag:*)"
  "Bash(git restore:*)" "Bash(git cherry-pick:*)" "Bash(git revert:*)" "Bash(git clean:*)"
)

# Same home as blind-triage.sh, for one findable place. Unlike blind-triage there is nothing to
# blind here — one phase, no context boundary — so the whole dir is granted back below.
OUT_DIR="${TRIAGE_HOME:-$HOME/.claude-triage}/$(date +%Y%m%d_%H%M%S)_${MODE}run"
mkdir -p "$OUT_DIR"
LOG="$OUT_DIR/transcript.jsonl"

if [[ "$MODE" == "why" ]]; then
  TRIGGER="WHY RUN"
  TOOLS="Bash,Read,Grep,Glob,Write,Skill,TodoWrite"
  SYS="You are executing the WHY RUN protocol headlessly. STOP AT THE DIAGNOSIS — do not propose a fix, do not open a file to edit, do not describe what you would change. State what ended the run and the evidence for it. CLAUDE.md's 'Before you open the first file' applies first: the run is evidence, not a work order."
else
  TRIGGER="FIX RUN"
  TOOLS="Bash,Read,Grep,Glob,Write,Edit,Skill,TodoWrite"
  SYS="You are executing the FIX RUN protocol headlessly. CLAUDE.md governs: ONE deadlock, <=150 changed lines across <=3 files, fix kinds (a)/(b)/(c) only — a new gate is not a fix. Ask the upstream question before any code. Author the change in the working tree and STOP; you may not run any git command that writes."
fi

PROMPT_FILE="$OUT_DIR/prompt.txt"
{
  echo "/fix-run"
  echo
  echo "$TRIGGER"
  [[ -n "$EXTRA_NOTE" ]] && { echo; printf '%s\n' "$EXTRA_NOTE"; }
  cat <<EOF

You are running HEADLESS from scripts/triage/fix-run.sh. There is no human here to answer a
question mid-run: if you would ask one, write it down as an open question and carry on with what
you can measure. Do not run /clear. You may not perform any git write — they are denied at the CLI.

Do NOT write, update or delete an auto-memory, and do not ask to. Memories load automatically into
every later session, including the phases of a blind-triage run, where they would bypass that
protocol's blinding entirely. Put anything worth keeping in your report instead.

/tmp is OUTSIDE the workspace and every write to it is blocked, including shell redirection
(\`> /tmp/out.txt\`). Use $OUT_DIR for scratch files, or a tool's own --out flag.

Write your final report — the diagnosis$( [[ "$MODE" == "fix" ]] && echo ", the fix, and the QA handoff" ) — to:
  $OUT_DIR/report.md
using the Write tool, in addition to printing it.
EOF
} > "$PROMPT_FILE"

printf '\n\033[1m%s\033[0m  · model=%s · case %s\n\n' "$TRIGGER" "$MODEL" "$OUT_DIR"

# `< /dev/null` because the prompt is an argument — otherwise the CLI waits on stdin. `--add-dir`
# because acceptEdits only auto-approves writes inside the workspace.
set +e
claude -p "$(cat "$PROMPT_FILE")" \
  --model "$MODEL" \
  --output-format stream-json --verbose \
  --permission-mode "$PERM_MODE" \
  --tools "$TOOLS" \
  --allowed-tools "Bash" "Read" "Grep" "Glob" "Write" \
  --disallowed-tools "${GIT_DENY[@]}" \
  --add-dir "$OUT_DIR" \
  --append-system-prompt "$SYS" \
  < /dev/null 2>&1 | tee "$LOG" | python3 "$STREAM_FILTER"
status=${PIPESTATUS[0]}
set -e

printf '\nreport:     %s\ntranscript: %s\n' "$OUT_DIR/report.md" "$LOG"
if [[ "$MODE" == "fix" ]]; then
  printf '\nThe change (if any) is UNCOMMITTED in your working tree. Review it with: git diff\n'
fi
exit "$status"
