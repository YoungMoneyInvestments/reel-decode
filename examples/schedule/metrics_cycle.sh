#!/usr/bin/env bash
# metrics_cycle.sh: the learning loop, unattended. Reads, never posts.
#   1. reeldecode learn pull     every posted brief whose 24 h / 72 h / 7 d mark is due
#   2. reeldecode learn report   rewrites LEARNINGS.md
#   3. optional: commits the changed briefs + LEARNINGS.md (set COMMIT=1)
# Exit code is non-zero when any post could not be read, so your scheduler can alert you.
#
# Usage: REELDECODE_PROJECT=/path/to/your/project ./metrics_cycle.sh
set -uo pipefail
PROJECT="${REELDECODE_PROJECT:?set REELDECODE_PROJECT to the folder holding reeldecode.toml}"
RD="${REELDECODE_BIN:-reeldecode}"
cd "$PROJECT" || exit 2
log() { echo "[$(date '+%F %T')] $*"; }

log "start"
"$RD" learn pull; pull_rc=$?
"$RD" learn report >/dev/null || { log "FAIL: learn report"; exit 1; }

if [ "${COMMIT:-0}" = "1" ] && git rev-parse --git-dir >/dev/null 2>&1; then
  if [ -n "$(git status --porcelain -- experiments LEARNINGS.md)" ]; then
    git add -- experiments LEARNINGS.md
    git commit -q -m "data(metrics): scheduled pull $(date '+%F %H:%M')" && log "committed new numbers"
    [ "${PUSH:-0}" = "1" ] && git push -q && log "pushed"
  else
    log "no new numbers due"
  fi
fi

if [ "$pull_rc" -ne 0 ]; then
  log "FAIL: some posts could not be read (exit $pull_rc); see the PROBLEM lines above"
  exit "$pull_rc"
fi
log "done"
