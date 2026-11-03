#!/usr/bin/env bash
# Bulk version of set_project_field.sh: applies many field writes to the "Tapio"
# project board (org project 2) while doing the project/field/item lookups only
# once each, instead of once per write. Use this for anything touching more than
# a handful of issues — set_project_field.sh's per-call lookups are fine for one
# or two issues, but calling it dozens of times in a loop re-fetches the same
# project, field, and item-list data every time and can trip GitHub's secondary
# GraphQL rate limit (an "abuse detection" cooldown, separate from and stricter
# than the plain per-hour limit, that can lock out further calls for several
# minutes once tripped).
#
# Usage: feed TSV lines of "<issue-number> <field-name> <value>" on stdin:
#   printf '15\tPriority\tP0\n15\tSize\tXL\n30\tPriority\tP0\n' | bulk_set_project_fields.sh
#
# A small delay is inserted between mutations as a further guard against the
# same rate limit.
set -euo pipefail

OWNER="Finntegrate"
PROJECT_NUMBER=2
REPO="Finntegrate/tapio"
DELAY_SECONDS=0.5

# Fetch every item on the board (#107). gh pages through the API up to --limit, so
# the limit starts well above the board's size; totalCount then says whether the
# board has outgrown it, in which case the items are fetched again at that exact
# count. Without this check an issue past the limit would be reported as "not on
# the board" rather than as a truncated lookup.
ITEM_LIMIT="${TAPIO_BOARD_ITEM_LIMIT:-1000}"
fetch_board_items() {
  local json total returned
  json=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json --limit "$ITEM_LIMIT")
  total=$(jq -r '.totalCount // empty' <<<"$json")
  returned=$(jq '.items | length' <<<"$json")
  if [[ -n "$total" && "$returned" -lt "$total" ]]; then
    json=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json --limit "$total")
    returned=$(jq '.items | length' <<<"$json")
  fi
  if [[ -n "$total" && "$returned" -lt "$total" ]] || [[ -z "$total" && "$returned" -ge "$ITEM_LIMIT" ]]; then
    echo "Fetched $returned of ${total:-at least $returned} project board items, so the lookup would be incomplete." \
      "Raise TAPIO_BOARD_ITEM_LIMIT (currently $ITEM_LIMIT) and try again." >&2
    return 1
  fi
  printf '%s' "$json"
}

PROJECT_ID=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json --jq '.id')
FIELDS_JSON=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json)
ITEMS_JSON=$(fetch_board_items)

while IFS=$'\t' read -r ISSUE_NUMBER FIELD_NAME VALUE; do
  [[ -z "${ISSUE_NUMBER:-}" ]] && continue

  FIELD_JSON=$(jq -c --arg name "$FIELD_NAME" '.fields[] | select(.name == $name)' <<<"$FIELDS_JSON")
  if [[ -z "$FIELD_JSON" ]]; then
    echo "SKIP #$ISSUE_NUMBER: no project field named '$FIELD_NAME'" >&2
    continue
  fi
  FIELD_ID=$(jq -r '.id' <<<"$FIELD_JSON")
  FIELD_TYPE=$(jq -r '.type' <<<"$FIELD_JSON")

  ITEM_ID=$(jq -r --arg repo "$REPO" --argjson num "$ISSUE_NUMBER" \
    '.items[] | select(.content.repository == $repo and .content.number == $num) | .id' <<<"$ITEMS_JSON")
  if [[ -z "$ITEM_ID" ]]; then
    echo "SKIP #$ISSUE_NUMBER: not found on the project board" >&2
    continue
  fi

  if [[ "$FIELD_TYPE" == "ProjectV2SingleSelectField" ]]; then
    OPTION_ID=$(jq -r --arg val "$VALUE" '.options[] | select(.name == $val) | .id' <<<"$FIELD_JSON")
    if [[ -z "$OPTION_ID" ]]; then
      echo "SKIP #$ISSUE_NUMBER: '$VALUE' is not a valid option for $FIELD_NAME" >&2
      continue
    fi
    gh project item-edit --id "$ITEM_ID" --field-id "$FIELD_ID" --project-id "$PROJECT_ID" \
      --single-select-option-id "$OPTION_ID" >/dev/null
  else
    gh project item-edit --id "$ITEM_ID" --field-id "$FIELD_ID" --project-id "$PROJECT_ID" \
      --text "$VALUE" >/dev/null
  fi

  echo "Set $FIELD_NAME = $VALUE on issue #$ISSUE_NUMBER."
  sleep "$DELAY_SECONDS"
done
