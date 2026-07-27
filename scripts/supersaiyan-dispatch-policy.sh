#!/usr/bin/env bash

# Print the only Ready issue eligible for a strict serial task chain.
#
# Done and Skipped cards are terminal and do not hold the chain. The
# lowest-numbered remaining issue owns the pipeline until it reaches a terminal
# column. If that issue is in Building, QA, Review, Blocked, or already claimed,
# no new Builder may start.
strict_serial_ready_issue() {
  local project_items_json="$1"
  jq -r '
    [
      .items[]
      | select(.content.type == "Issue")
      | select(.status != "Done" and .status != "Skipped")
    ]
    | sort_by(.content.number)
    | first
    | select(
        .status == "Ready"
        and ((.content.assignees // []) | length == 0)
      )
    | .content.number // empty
  ' <<<"$project_items_json"
}

offline_dispatch_available() {
  [ ! -f "$1/$2.offline-dispatched" ]
}

mark_offline_dispatch() {
  mkdir -p "$1"
  : >"$1/$2.offline-dispatched"
}
