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

PROJECT_ID=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json --jq '.id')
FIELDS_JSON=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json)
ITEMS_JSON=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json --limit 200)

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
