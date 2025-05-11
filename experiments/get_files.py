#!/usr/bin/env python3

import sys
import os
import glob
import re

EXT_LANG = {
    "py": "python",
    "sh": "bash",
    "js": "javascript",
    "ts": "typescript",
    "rb": "ruby",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "h": "c",
    "hpp": "cpp",
    "go": "go",
    "rs": "rust",
    "php": "php",
    "html": "html",
    "css": "css",
    "json": "json",
    "yml": "yaml",
    "yaml": "yaml",
    "md": "markdown",
    "txt": "plaintext",
    "pl": "perl",
}

def guess_language(filename):
    ext = os.path.splitext(filename)[1][1:].lower()
    return EXT_LANG.get(ext, "plaintext") if ext else "plaintext"

def resolve_targets(targets):
    resolved_files = set() # Use a set to avoid duplicates
    unmatched = []
    for target in targets:
        target = target.strip()
        if not target:
            continue

        found_match_for_target = False

        # --- Check for wildcards first ---
        if any(c in target for c in "*?[]"): # Check for glob characters
            # Use glob.glob with recursive=True for ** support
            # Note: glob behavior might be case-sensitive on Unix, case-insensitive on Windows
            try:
                # Use recursive=True to handle '**' correctly
                glob_matches = glob.glob(target, recursive=True)
                found_files_for_glob = False
                for potential_match in glob_matches:
                    # Important: glob can return directories, filter for files
                    if os.path.isfile(potential_match):
                        resolved_files.add(os.path.normpath(potential_match))
                        found_files_for_glob = True
                        found_match_for_target = True # Mark that this target yielded *some* result

                # If the glob pattern was processed but found no *files*, mark the pattern as unmatched
                # Note: This doesn't add to unmatched if glob itself fails, only if it returns 0 files (or only dirs)
                if not found_files_for_glob:
                     # We defer adding to unmatched until the end of the loop for this target
                     pass # Let the final check handle it

            except Exception as e:
                print(f"# Warning: Error processing glob pattern '{target}': {e}", file=sys.stderr)
                # Treat as unmatched if glob processing fails
                # unmatched.append(target) # Let the final check handle it


        # --- If not a wildcard, proceed with existing logic ---
        # Absolute or existing relative path (containing path separators)
        elif os.path.isabs(target) or os.path.sep in target or (os.altsep and os.altsep in target):
            normalized = os.path.normpath(target)
            if os.path.isfile(normalized):
                resolved_files.add(normalized)
                found_match_for_target = True
            # else: It's a path but not a file, will be added to unmatched below if found_match_for_target remains False

        # Filename only, search for it recursively, case-insensitive
        else:
            matches = []
            try:
                for root, _, files in os.walk("."):
                    for f in files:
                        # Use os.path.basename to handle potential path components in f
                        # Though os.walk usually provides just filenames in files list
                        if f.lower() == target.lower():
                            matches.append(os.path.normpath(os.path.join(root, f)))
            except Exception as e:
                 print(f"# Warning: Error during recursive search for '{target}': {e}", file=sys.stderr)

            if matches:
                resolved_files.update(matches) # Add all found matches
                found_match_for_target = True
            # else: No matches found via recursive search, will be added to unmatched below

        # --- Final check for this target ---
        # If after all checks (glob, path, recursive filename), no file was resolved
        # for *this specific target string*, add the original target string to unmatched.
        if not found_match_for_target:
             unmatched.append(target)

    # Convert set to sorted list for consistent output order
    return sorted(list(resolved_files)), unmatched

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} \"file1.py,dir/file2.py,*.txt,src/**/*.js,...\"") # Updated usage
        sys.exit(1)
    # Split by comma and/or any whitespace
    targets = [x.strip() for x in re.split(r'[,\s]+', sys.argv[1]) if x.strip()]
    if not targets:
        print("No valid filenames, paths, or patterns supplied.")
        sys.exit(1)

    files, unmatched = resolve_targets(targets)
    printed_any = False

    for path in files:
        # Defensive check: Ensure it's still a file (e.g., could be deleted between glob and open)
        if not os.path.isfile(path):
            print(f"# Warning: '{path}' existed but is no longer a file.", file=sys.stderr)
            continue

        rel_path = os.path.relpath(path, ".")
        lang = guess_language(path)
        if printed_any:
            print("\n\n", end="")
        printed_any = True
        code_header = f"```{lang}" if lang else "```"
        print(f"{code_header}\n# {rel_path}\n")
        try:
            # Handle potential encoding issues, fallback if needed
            try:
                with open(path, "r", encoding="utf-8") as file:
                    print(file.read(), end="")
            except UnicodeDecodeError:
                print(f"# Warning: Could not decode {rel_path} as UTF-8. Trying latin-1.", file=sys.stderr)
                try:
                     with open(path, "r", encoding="latin-1") as file:
                         print(file.read(), end="")
                except Exception as inner_e:
                     print(f"# Error reading {rel_path} (even with fallback): {inner_e}")

        except Exception as e:
            print(f"# Error reading {rel_path}: {e}")
        print("\n```")

    # Print unmatched targets at the end
    if unmatched:
        if printed_any: print("\n") # Add separator if files were printed
        print("# --- Warnings ---")
        for target in unmatched:
            print(f"# Target not found or pattern yielded no files: '{target}'")

    if not printed_any and not unmatched:
         # This case should ideally not happen if input validation works, but good to have.
         print("# No files found matching the targets or patterns.")
    elif not printed_any and unmatched:
         # Only print this specific message if only unmatched targets were found
         print("# No files found matching the target filenames, paths or patterns.")


if __name__ == "__main__":
    main()
