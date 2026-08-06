#!/usr/bin/env bash
set -euo pipefail

# Stop only the OA backend started by process-compose.  Do not use a broad
# `pkill java`: the developer machine may have unrelated Java services.
target='yudao-server/target/yudao-server.jar'
declare -a pids=()

while IFS= read -r pid; do
  [[ -n "$pid" ]] && pids+=("$pid")
done < <(
  ps -axo pid=,comm=,command= | awk -v target="$target" '
    {
      # The command line that invokes this cleanup script also contains the
      # jar text.  Require the executable name to be java so that the cleanup
      # never kills its own shell or the process-compose supervisor.
      if ($2 !~ /(^|\/)java$/) next
      for (i = 3; i <= NF; i++) {
        if ($i == "-jar" && (i + 1) <= NF && $(i + 1) == target) {
          print $1
          break
        }
      }
    }'
)

if [[ "${#pids[@]}" -eq 0 ]]; then
  exit 0
fi

printf 'stopping OA Java backend PID(s): %s\n' "${pids[*]}" >&2
kill -TERM "${pids[@]}" 2>/dev/null || true

deadline=$((SECONDS + 10))
while (( SECONDS < deadline )); do
  alive=()
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      alive+=("$pid")
    fi
  done
  [[ "${#alive[@]}" -eq 0 ]] && exit 0
  sleep 1
done

# The PID list was captured using the exact jar matcher above; only those
# processes may receive the final KILL.
for pid in "${pids[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    printf 'force-stopping OA Java backend PID %s after timeout\n' "$pid" >&2
    kill -KILL "$pid" 2>/dev/null || true
  fi
done
