#!/bin/bash

SCRIPT_NAME=$(basename "$0")
PRINT_SEPARATOR=false

# If you want to exclude specific files or directories, list them here.
# For directories, append a trailing slash (e.g., "repos/").
# For files, simply put the file name (e.g., "ignore_me.py").
EXCLUDED_FILES=("repos/")

# Use find to recursively locate all .py files.
# -print0 with while IFS= read -r -d '' avoids issues with spaces in filenames.
find . -type f -name "*.py" -print0 | while IFS= read -r -d '' file; do

  # Strip leading "./" to produce a clean relative path.
  rel_path="${file#./}"

  # Loop over each exclusion pattern in EXCLUDED_FILES.
  for pattern in "${EXCLUDED_FILES[@]}"; do
    if [[ "$pattern" == */ ]]; then
      # If the pattern ends with a slash, exclude files in that directory.
      if [[ "$rel_path" == "$pattern"* ]]; then
        # Skip this file altogether.
        continue 2
      fi
    else
      # Otherwise, exclude by file name.
      if [[ "$(basename "$file")" == "$pattern" ]]; then
        continue 2
      fi
    fi
  done

  # Print a blank separator before each subsequent file.
  if $PRINT_SEPARATOR; then
    printf "\n\n"
  fi
  PRINT_SEPARATOR=true

  # Check the first two lines for a line exactly matching "# <relative path>"
  # (e.g., "# some/path/to/file.py").
  line1="$(head -n 1 "$file" 2>/dev/null)"
  line2="$(head -n 2 "$file" 2>/dev/null | tail -n 1)"
  alreadyHasPath=false
  if [[ "$line1" == "# $rel_path" || "$line2" == "# $rel_path" ]]; then
    alreadyHasPath=true
  fi

  # Print the code block (Markdown style).
  printf "\`\`\`python\n"
  # If the file does NOT already contain the “# <relative path>” line near the top, print it.
  if ! $alreadyHasPath; then
    printf "# %s\n\n" "$rel_path"
  fi

  # Print the file contents.
  cat "$file"

  # Close the Markdown code block.
  printf "\n\`\`\`\n"
done
