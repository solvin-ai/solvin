#!/bin/bash

#❯ git fetch origin 8ba28b76105faf465d5c5331643571376aa8e7d6
#❯ git rev-parse 8ba28b76105faf465d5c5331643571376aa8e7d6^
#❯ git checkout c866c8384b8da4cb4c9fdd5e12c3c1c91a247c78
#❯ git checkout -b pre-merge-branch

# --- Configuration ---
# Branch name to create/reset at the parent of the first PR commit
NEW_BRANCH_NAME="pre-merge-branch"
# The remote repository name to fetch from (usually "origin")
REMOTE_NAME="origin"

# --- Function for error handling ---
error_exit() {
    echo "Error: $1" >&2
    # If we stashed changes, attempt to restore them before exiting
    if [ "$STASHED" = true ]; then
        echo "Attempting to restore stashed changes before exit..."
        # Best effort pop - might fail if checkout failed badly or if conflicts exist
        git stash pop --quiet || echo "Warning: Failed to pop stashed changes automatically on error exit. Use 'git stash list' and 'git stash pop/apply'."
    fi
    exit 1
}

# --- Dependency Check ---
# Ensure GitHub CLI ('gh') is installed and available
if ! command -v gh &> /dev/null; then
    error_exit "GitHub CLI ('gh') could not be found. Please install it (https://cli.github.com/) and authenticate ('gh auth login')."
fi
# Ensure 'jq' (JSON processor) is installed and available
if ! command -v jq &> /dev/null; then
    error_exit "'jq' command could not be found. Please install jq (e.g., 'sudo apt-get install jq' or 'brew install jq')."
fi
echo "Checked: 'gh' and 'jq' are available."

# --- Input Validation ---
# Check if an argument (issue number) was provided
if [ -z "$1" ]; then
  error_exit "Usage: $(basename "$0") <issue_number>"
fi
# Remove potential leading '#' if the user included it
ISSUE_NUMBER="${1#\#}"
# Basic check if the input looks like a number
if ! [[ "$ISSUE_NUMBER" =~ ^[0-9]+$ ]]; then
    error_exit "Invalid issue number format: '$1'. Please provide a numeric issue number."
fi
echo "Input: Issue Number ${ISSUE_NUMBER}"


# --- Environment Check ---
# Verify we are inside a Git repository
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    error_exit "Not inside a Git repository. Please 'cd' into your repository first."
fi
# Determine repository NWO (name with owner) for gh commands using gh itself
REPO_NWO=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)
# Fallback: try to get NWO from git remote URL if gh command failed
if [ -z "$REPO_NWO" ]; then
    REMOTE_URL=$(git config --get "remote.${REMOTE_NAME}.url")
    # Extract owner/repo pattern from common Git URL formats
    if [[ "$REMOTE_URL" =~ github\.com[/:]([^\/]+\/[^\/]+?)(\.git)?$ ]]; then
        REPO_NWO="${BASH_REMATCH[1]}"
        echo "Info: Determined repository owner/name from git remote URL: ${REPO_NWO}"
    else
       error_exit "Could not determine repository owner/name using 'gh repo view' or git remote URL. Ensure you are in a repo linked to GitHub and 'gh' is authenticated or remote '${REMOTE_NAME}' points to GitHub."
    fi
fi
echo "Checked: Running inside a Git repository (${REPO_NWO})."

# --- Find PR and First Commit ---
echo "Searching for PRs mentioning issue #${ISSUE_NUMBER} in ${REPO_NWO}..."
# Use gh search prs, searching for the text "#<issue_number>".
# WARNING: This is less precise than "links:" and might find PRs that only mention the number.
# Request number, title, state for context and filtering.
# Don't filter by state here; we'll filter the JSON result.
PR_SEARCH_RAW_JSON=$(gh search prs --repo "$REPO_NWO" "#${ISSUE_NUMBER}" --json number,title,state --limit 20 2>/dev/null)

# Check if the search itself failed or returned empty JSON (jq handles empty input gracefully)
if [ -z "$PR_SEARCH_RAW_JSON" ]; then
     # This could mean gh command failed OR no PRs found mentioning the number. Verify issue exists.
     echo "Info: 'gh search prs' for text '#${ISSUE_NUMBER}' returned no data. Verifying issue exists..."
     if ! gh issue view "$ISSUE_NUMBER" --repo "$REPO_NWO" --comments=false > /dev/null 2>&1; then
         error_exit "Failed to find issue #${ISSUE_NUMBER} in repo ${REPO_NWO}."
     else
         # Issue exists, so no PRs mentioning it were found by the search.
         error_exit "No Pull Request found mentioning issue #${ISSUE_NUMBER} in repo ${REPO_NWO}."
     fi
fi

# Filter the results using jq to keep only open or merged PRs
# Use lowercase states as returned by gh search prs
PR_SEARCH_RESULTS_JSON=$(echo "$PR_SEARCH_RAW_JSON" | jq '[.[] | select(.state == "open" or .state == "merged")]')

# Count how many relevant PRs were found after filtering
PR_COUNT=$(echo "$PR_SEARCH_RESULTS_JSON" | jq 'length')

if [ "$PR_COUNT" -eq 0 ]; then
     # No PRs matched the open or merged criteria after filtering
     error_exit "No OPEN or MERGED Pull Request found mentioning issue #${ISSUE_NUMBER}."
elif [ "$PR_COUNT" -gt 1 ]; then
    echo "Warning: Found multiple (${PR_COUNT}) OPEN or MERGED PRs mentioning issue #${ISSUE_NUMBER}:"
    # Print details of the found PRs
    echo "$PR_SEARCH_RESULTS_JSON" | jq -r '.[] | "- PR #" + (.number | tostring) + " (" + .state + "): " + .title'
    # Take the first one listed by the search (often sorted by relevance/most recent, but not guaranteed)
    PR_NUMBER=$(echo "$PR_SEARCH_RESULTS_JSON" | jq -r '.[0].number') # Get number of the first PR in the array
    echo "Proceeding with the first listed PR found: #${PR_NUMBER}"
else
    # Exactly one relevant PR found
    PR_NUMBER=$(echo "$PR_SEARCH_RESULTS_JSON" | jq -r '.[0].number')
    PR_TITLE=$(echo "$PR_SEARCH_RESULTS_JSON" | jq -r '.[0].title')
    PR_STATE=$(echo "$PR_SEARCH_RESULTS_JSON" | jq -r '.[0].state')
    echo "Found matching Pull Request: #${PR_NUMBER} (${PR_STATE}): ${PR_TITLE}"
fi


echo "Fetching commit list for PR #${PR_NUMBER}..."
# Get commits for the found PR number.
# The first commit in the list returned by the API is usually the earliest chronologically.
# Use '-q' for cleaner output extraction with jq.
FIRST_COMMIT_HASH=$(gh pr view "$PR_NUMBER" --repo "$REPO_NWO" --json commits -q '.commits[0].oid' 2>/dev/null)

# Validate that a commit hash was retrieved
if [ -z "$FIRST_COMMIT_HASH" ] || [ "$FIRST_COMMIT_HASH" == "null" ]; then
    # Check if the PR exists but might be empty or had an API issue retrieving commits
    if gh pr view "$PR_NUMBER" --repo "$REPO_NWO" > /dev/null 2>&1; then
        error_exit "Could not retrieve commits for PR #${PR_NUMBER}. The PR might be empty or there was an API issue."
    else
        # This case is less likely if we successfully found the PR number moments ago
        error_exit "Failed to view PR #${PR_NUMBER} after initially finding it."
    fi
fi

echo "Found first commit hash for PR #${PR_NUMBER}: ${FIRST_COMMIT_HASH}"
TARGET_COMMIT="${FIRST_COMMIT_HASH}" # Assign the found hash to the variable used below

# --- Git Operations ---

echo "Fetching specific commit object: ${TARGET_COMMIT} from ${REMOTE_NAME}..."
# Attempt a shallow fetch first (fetch only the specific commit object)
if ! git fetch "${REMOTE_NAME}" "${TARGET_COMMIT}" --no-tags --quiet --no-recurse-submodules --depth=1; then
  # If shallow fetch failed (e.g., server doesn't support it well, or commit isn't advertised), try a deeper fetch
  echo "Info: Initial shallow fetch failed or returned non-zero, trying a deeper fetch..."
  if ! git fetch "${REMOTE_NAME}" "${TARGET_COMMIT}" --no-tags --quiet; then
    error_exit "Failed to fetch commit ${TARGET_COMMIT} from ${REMOTE_NAME}. Hint: Check remote, network, permissions, and if the commit exists on the remote and is reachable."
  fi
fi
echo "Fetch successful. Target commit object should be available locally."

# Verify the target commit object is indeed present locally after fetching
if ! git rev-parse --verify "${TARGET_COMMIT}^{commit}" > /dev/null 2>&1; then
    error_exit "Fetched commit object ${TARGET_COMMIT} could not be verified locally after fetch."
fi
echo "Commit object ${TARGET_COMMIT} verified locally."

echo "Inspecting commit ${TARGET_COMMIT} to find its parent..."
# Use git cat-file to print the commit object's content
# Grep for the first 'parent' line (most commits, except root commits, have at least one)
# Use awk to extract the second field (the parent commit hash)
# This assumes the first commit in the PR is not a merge commit itself (usually true)
PARENT_COMMIT=$(git cat-file -p "${TARGET_COMMIT}" | grep '^parent ' | head -n 1 | awk '{print $2}')

# Check if we successfully extracted a parent hash
if [ -z "${PARENT_COMMIT}" ]; then
    # Check if the reason is that it's a root commit (no 'parent' lines at all)
    if ! git cat-file -p "${TARGET_COMMIT}" | grep -q '^parent '; then
      echo "Warning: Could not find parent commit line for ${TARGET_COMMIT}. This might be the initial commit in the repository or an unusual history structure."
      # In this ambiguous case, we'll try checking out the target commit itself, but warn the user.
      PARENT_COMMIT="${TARGET_COMMIT}" # Use the target commit as the checkout target
      echo "Will attempt to check out the commit ${TARGET_COMMIT} directly, but this might not represent the state *before* the PR changes."
    else
      # We found 'parent' lines but failed to parse one - possibly a merge commit or unexpected format
      error_exit "Failed to parse a single parent commit hash from 'git cat-file -p ${TARGET_COMMIT}'. Commit might have multiple parents."
    fi
else
  echo "Parent commit found: ${PARENT_COMMIT}"

  # Fetch the parent commit object to ensure it's available locally for checkout
  # (it might not have been fetched if the initial fetch was shallow)
  echo "Fetching parent commit object ${PARENT_COMMIT} from ${REMOTE_NAME}..."
  # Try shallow first, then deeper if needed. Ignore errors, as it might already exist locally.
  git fetch "${REMOTE_NAME}" "${PARENT_COMMIT}" --no-tags --quiet --no-recurse-submodules --depth=1 || \
  git fetch "${REMOTE_NAME}" "${PARENT_COMMIT}" --no-tags --quiet || true

  # Verify the parent commit object is now local
  if ! git rev-parse --verify "${PARENT_COMMIT}^{commit}" > /dev/null 2>&1; then
       error_exit "Parent commit object ${PARENT_COMMIT} could not be verified locally, even after attempting to fetch it."
  fi
  echo "Parent commit object ${PARENT_COMMIT} verified locally."
fi


# --- Perform Checkout ---
# Stash any local uncommitted changes to prevent checkout conflicts
STASHED=false # Flag to track if we created a stash
# Check for both unstaged and staged changes
if ! git diff --quiet --exit-code || ! git diff --cached --quiet --exit-code; then
    echo "Warning: Uncommitted changes detected. Stashing them..."
    # Create a unique stash message
    STASH_MESSAGE="Temp stash by script $(basename "$0") - $(date)"
    if git stash push -m "$STASH_MESSAGE"; then
        STASHED=true
        echo "Changes stashed with message: '$STASH_MESSAGE'"
    else
        # Attempt stash pop before exiting on checkout failure
        error_exit "Failed to stash changes. Please commit or stash them manually before running the script."
    fi
fi

# Determine which commit to checkout: the parent, or the target itself if no distinct parent was found
CHECKOUT_TARGET="${PARENT_COMMIT}" # Default to parent
if [ "${PARENT_COMMIT}" == "${TARGET_COMMIT}" ]; then
  echo "Checking out the target commit itself (as no distinct parent was found): ${CHECKOUT_TARGET}..."
else
  echo "Checking out parent commit: ${CHECKOUT_TARGET}..."
fi

# Perform the checkout in detached HEAD state to avoid affecting any existing branch
if ! git checkout --detach "${CHECKOUT_TARGET}"; then
    # If checkout fails, attempt to restore stashed changes before exiting
    error_exit "Failed to checkout commit ${CHECKOUT_TARGET}."
fi
echo "Checkout of commit ${CHECKOUT_TARGET} successful (detached HEAD)."

# *** MODIFICATION FOR REPEATED RUNS ***
# Remove the check for existing branch - we will overwrite/reset it.
# echo "Creating new branch '${NEW_BRANCH_NAME}' from current HEAD (${CHECKOUT_TARGET})..."
# If branch exists, reset it. If not, create it. Use -B.
echo "Ensuring branch '${NEW_BRANCH_NAME}' points to current HEAD (${CHECKOUT_TARGET})..."
if ! git checkout -B "${NEW_BRANCH_NAME}"; then
    # If branch creation/reset fails, attempt to restore stashed changes before exiting
    error_exit "Failed to create or reset branch ${NEW_BRANCH_NAME}."
fi
echo "Successfully created or reset branch '${NEW_BRANCH_NAME}'."


# Pop the stash if we created one earlier
if [ "$STASHED" = true ]; then
    echo "Restoring stashed changes..."
    if ! git stash pop; then
       # Don't exit if pop fails (e.g., conflicts), just warn the user
       echo "Warning: Failed to automatically pop stashed changes. There might be conflicts."
       echo "Use 'git status' to check and 'git stash list' to see the stash."
    else
       echo "Stashed changes restored successfully."
    fi
fi

echo ""
echo "Script finished successfully."
echo "You are now on branch '${NEW_BRANCH_NAME}' which points to commit ${CHECKOUT_TARGET} (the parent of the first commit in PR #${PR_NUMBER})."
exit 0
