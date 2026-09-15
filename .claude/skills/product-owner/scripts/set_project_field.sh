#!/usr/bin/env bash
# Sets a Priority, Size, Status, or Milestone field on a Finntegrate/tapio issue's
# card in the "Tapio" project board (org project 2 — the tapio-scoped board, not
# the broader multi-repo "Finntegrate Team" project 1).
#
# Usage: set_project_field.sh <issue-number> <field-name> <value>
#   set_project_field.sh 45 Priority P1
#   set_project_field.sh 45 Size M
#   set_project_field.sh 45 Milestone "Durable conversations"
#
# Priority/Size/Status are single-select fields: the value must match one of the
# board's existing option names exactly (case-sensitive). Milestone is free text,
# so any string is accepted. The project fields (and their options) can change on
# the board over time, so this looks them up live rather than hardcoding IDs.
set -euo pipefail

ISSUE_NUMBER="${1:?usage: set_project_field.sh <issue-number> <field-name> <value>}"
FIELD_NAME="${2:?usage: set_project_field.sh <issue-number> <field-name> <value>}"
VALUE="${3:?usage: set_project_field.sh <issue-number> <field-name> <value>}"

OWNER="Finntegrate"
PROJECT_NUMBER=2
REPO="Finntegrate/tapio"

PROJECT_ID=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json --jq '.id')

FIELD_JSON=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json \
  | jq -c --arg name "$FIELD_NAME" '.fields[] | select(.name == $name)')

if [[ -z "$FIELD_JSON" ]]; then
  echo "No project field named '$FIELD_NAME'. Available fields:" >&2
  gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json | jq -r '.fields[].name' >&2
  exit 1
fi

FIELD_ID=$(jq -r '.id' <<<"$FIELD_JSON")
FIELD_TYPE=$(jq -r '.type' <<<"$FIELD_JSON")

ITEM_ID=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json --limit 200 \
  | jq -r --arg repo "$REPO" --argjson num "$ISSUE_NUMBER" \
    '.items[] | select(.content.repository == $repo and .content.number == $num) | .id')

if [[ -z "$ITEM_ID" ]]; then
  echo "Issue #$ISSUE_NUMBER not found on the project board. It should auto-add on creation (see CLAUDE.md) — check it exists and try again in a moment." >&2
  exit 1
fi

if [[ "$FIELD_TYPE" == "ProjectV2SingleSelectField" ]]; then
  OPTION_ID=$(jq -r --arg val "$VALUE" '.options[] | select(.name == $val) | .id' <<<"$FIELD_JSON")
  if [[ -z "$OPTION_ID" ]]; then
    echo "'$VALUE' is not a valid option for $FIELD_NAME. Valid options:" >&2
    jq -r '.options[].name' <<<"$FIELD_JSON" >&2
    exit 1
  fi
  gh project item-edit --id "$ITEM_ID" --field-id "$FIELD_ID" --project-id "$PROJECT_ID" \
    --single-select-option-id "$OPTION_ID" >/dev/null
else
  gh project item-edit --id "$ITEM_ID" --field-id "$FIELD_ID" --project-id "$PROJECT_ID" \
    --text "$VALUE" >/dev/null
fi

echo "Set $FIELD_NAME = $VALUE on issue #$ISSUE_NUMBER."
