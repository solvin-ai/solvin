#!/usr/bin/env bash
set -euo pipefail

# 1) Change me to your real DB path
DB=../../../../data/dbs/agents.db
#!/usr/bin/env bash

# 2) Backup
cp "$DB" "$DB.bak"
echo "Backed up to $DB.bak"

# 3) Pull the column‐lists once
declare -A COLUMNS
for tbl in agents_running agents_current turns tool_meta messages agent_state; do
  COLUMNS[$tbl]="$(sqlite3 "$DB" "PRAGMA table_info('$tbl');" \
                    | cut -d'|' -f2 \
                    | tr '\n' ' ')"
done

# 4) Build one big SQL script
SQL="PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
"

for tbl in "${!COLUMNS[@]}"; do
  cols=(${COLUMNS[$tbl]})
  has_name=0 has_url=0
  for c in "${cols[@]}"; do
    [[ $c == repo_name ]] && has_name=1
    [[ $c == repo_url  ]] && has_url=1
  done

  if (( has_name )); then
    if (( has_url )); then
      echo "→ $tbl: dropping old repo_name"
      SQL+="ALTER TABLE $tbl DROP COLUMN repo_name;
"
    else
      echo "→ $tbl: renaming repo_name → repo_url"
      SQL+="ALTER TABLE $tbl RENAME COLUMN repo_name TO repo_url;
"
    fi
  else
    echo "→ $tbl: no repo_name, skipping"
  fi
done

SQL+="COMMIT;
PRAGMA foreign_keys=ON;
"

# 5) Execute it all in one shot
printf "%s\n" "$SQL" | sqlite3 "$DB"

echo "Done."
