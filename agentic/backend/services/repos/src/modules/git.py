# modules/git.py

"""
This module clones/updates Git repositories and ensures that you are on the
configured branch. Submodules are updated only on a fresh clone.
If branch is not provided, the module automatically determines the default branch.
If dest_name (i.e. the repo name) is not provided, it is derived from the repo URL.
"""

import subprocess
import os
import re
from pathlib import Path
from typing import Optional
from shared.logger import logger

logger = logger
from shared.config import config

class GitRepo:
    def __init__(self, repo_url: str, branch: Optional[str] = None, dest_name: Optional[str] = None):
        # Ensure we are always using HTTPS URLs.
        self.repo_url = self._ensure_https_repo_url(repo_url)
        
        # If no branch is provided, determine it automatically.
        if not branch:
            branch = self._get_default_branch()
        self.branch = branch

        # Derive destination name from the URL if not provided.
        if dest_name is None:
            dest_name = self._parse_repo_name(self.repo_url)
        self.dest_name = dest_name

        # Retrieve the REPOS_DIR using the proper scope.
        self.base_dir = Path(config["REPOS_DIR"])
        self.dest_path = self.base_dir / self.dest_name

        self.first_clone = False
        logger.trace("Initialized GitRepo for URL: %s on branch: '%s'", self.repo_url, self.branch)

    def _ensure_https_repo_url(self, url: str) -> str:
        """
        Convert an SSH Git URL to its HTTPS equivalent.
        For example:
          git@github.com:user/repo.git --> https://github.com/user/repo.git
          ssh://git@github.com/user/repo.git --> https://github.com/user/repo.git
        """
        if url.startswith("git@"):
            https_url = url.replace("git@", "https://", 1)
            if ":" in https_url:
                parts = https_url.split(":", 1)
                https_url = parts[0] + "/" + parts[1]
            logger.trace("Converted SSH URL to HTTPS: %s", https_url)
            return https_url
        if url.startswith("ssh://"):
            https_url = url.replace("ssh://git@", "https://", 1)
            logger.trace("Converted SSH URL to HTTPS: %s", https_url)
            return https_url
        return url

    def _parse_repo_name(self, repo_url: str) -> str:
        repo_name = repo_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        logger.trace("Parsed repository name: %s", repo_name)
        return repo_name

    def _get_default_branch(self) -> str:
        """
        Determines the default branch of the remote repository.
        Uses 'git ls-remote --symref <repo_url> HEAD' to find the default branch.
        If detection fails, defaults to "main".
        """
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--symref", self.repo_url, "HEAD"],
                capture_output=True, text=True, check=True
            )
            # Look for a line that starts with "ref:" and contains "refs/heads/"
            for line in result.stdout.splitlines():
                if line.startswith("ref:"):
                    tokens = line.split()
                    if len(tokens) >= 2 and tokens[1].startswith("refs/heads/"):
                        # Using removeprefix if available (Python 3.9+)
                        default_branch = tokens[1].removeprefix("refs/heads/")
                        logger.trace("Detected default branch: %s", default_branch)
                        return default_branch
            logger.debug("Default branch not found in ls-remote output; defaulting to 'main'.")
            return "main"
        except Exception as e:
            logger.debug("Could not determine default branch, defaulting to 'main': %s", e)
            return "main"

    def run_git_command(self, args: list, *, capture_output: bool = False, text: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        cmd = ["git", "-C", str(self.dest_path)] + args
        logger.debug("Running git command: %s", " ".join(cmd))
        return subprocess.run(cmd, capture_output=capture_output, text=text, check=check)

    def remote_branch_exists(self, branch: str) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.dest_path), "ls-remote", "--heads", "origin", branch],
                capture_output=True, text=True, check=True
            )
            exists = bool(result.stdout.strip())
            logger.trace("Remote branch '%s' exists: %s", branch, exists)
            return exists
        except subprocess.CalledProcessError as e:
            logger.debug("Error checking remote branch '%s': %s", branch, e)
            return False

    def has_local_changes(self) -> bool:
        try:
            result = self.run_git_command(["status", "--porcelain"], capture_output=True)
            changes = bool(result.stdout.strip())
            logger.trace("Local changes present: %s", changes)
            return changes
        except Exception as e:
            logger.debug("Error checking for local changes: %s", e)
            return True

    def is_valid_git_repo(self):
        """Check if self.dest_path is a valid git repo (by testing git status)"""
        git_dir = self.dest_path / '.git'
        if not git_dir.exists():
            return False
        try:
            # This verifies it's a working git repo
            self.run_git_command(['status'], capture_output=True)
            logger.trace("Validated that %s is a valid Git repository.", self.dest_path)
            return True
        except Exception as exc:
            logger.warning("Directory exists but is not a valid Git repo: %s (error: %s)", self.dest_path, exc)
            return False

    def clone_repo(self) -> None:
        subprocess.run(["git", "clone", self.repo_url, str(self.dest_path)], check=True)
        logger.info("Cloned repository: %s", self.repo_url)

    def update_repo(self) -> None:
        self.run_git_command(["fetch"])
        if self.has_local_changes():
            logger.debug("Local changes detected; skipping update to avoid conflicts.")
            return

        if not self.remote_branch_exists(self.branch):
            logger.debug("Remote branch 'origin/%s' does not exist; skipping pull.", self.branch)
            return

        local_commit = self.run_git_command(["rev-parse", "HEAD"], capture_output=True).stdout.strip()
        try:
            remote_commit = self.run_git_command(["rev-parse", "@{u}"], capture_output=True).stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.debug("Unable to determine remote commit; skipping pull. Error: %s", e)
            return

        if local_commit != remote_commit:
            self.run_git_command(["pull"])
            logger.debug("Repository updated with new commits from remote.")
        else:
            logger.debug("Repository is already up-to-date.")

    def ensure_repo(self) -> None:
        self.base_dir.mkdir(mode=0o755, exist_ok=True)
        if self.dest_path.exists() and any(self.dest_path.iterdir()):
            if not self.is_valid_git_repo():
                logger.warning("Destination '%s' exists but is not a valid Git repository. Removing...", self.dest_path)
                import shutil
                shutil.rmtree(self.dest_path)
                logger.info("Removed invalid repo directory: %s", self.dest_path)
                self.clone_repo()
                self.first_clone = True
            else:
                self.first_clone = False
                logger.trace("Repository exists locally; performing update.")
                self.update_repo()
        else:
            logger.trace("Repository not found locally; cloning.")
            self.clone_repo()
            self.first_clone = True

    def switch_branch(self) -> None:
        branch = self.branch
        result = self.run_git_command(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], capture_output=True, check=False)
        if result.returncode == 0:
            logger.debug("Local branch '%s' exists. Checking it out.", branch)
            self.run_git_command(["checkout", branch])
        else:
            logger.debug("Local branch '%s' does not exist. Creating branch.", branch)
            if self.remote_branch_exists(branch):
                try:
                    self.run_git_command(["checkout", "-b", branch, f"origin/{branch}"])
                except subprocess.CalledProcessError:
                    self.run_git_command(["checkout", "-b", branch])
            else:
                self.run_git_command(["checkout", "-b", branch])

        if self.remote_branch_exists(branch):
            try:
                self.run_git_command(["branch", "--set-upstream-to", f"origin/{branch}", branch])
            except subprocess.CalledProcessError as e:
                logger.debug("Failed to set upstream for branch '%s': %s", branch, e)
        logger.trace("Now on branch '%s'.", branch)

    def update_submodules(self) -> None:
        gitmodules = self.dest_path / ".gitmodules"
        if gitmodules.exists():
            content = gitmodules.read_text()
            updated_content = re.sub(r"url\s*=\s*git@([^:]+):", r"url = https://\1/", content)
            gitmodules.write_text(updated_content)
            logger.trace("Updated .gitmodules to use HTTPS for submodules.")

            self.run_git_command(["submodule", "sync", "--recursive"])
            self.run_git_command(["submodule", "deinit", "--force", "."])
            self.run_git_command(["submodule", "update", "--init", "--recursive"])
            logger.debug("Submodules updated successfully.")

    def setup(self) -> Path:
        self.ensure_repo()
        self.switch_branch()
        if self.first_clone:
            self.update_submodules()
        return self.dest_path

def clone_repo(repo_url: str, branch: Optional[str] = None, dest_name: Optional[str] = None) -> str:
    """
    Clones or updates a Git repository under the "repos" directory.
    Branch is optional; if not provided, the default branch (as determined from the remote)
    is used. If dest_name is provided, the repository is cloned into that directory name;
    otherwise, it is derived from the repo URL.
    Returns the local repository path.
    If the real git clone fails, fall back to creating an empty directory.
    """
    # Determine REPOS_DIR
    base = Path(config["REPOS_DIR"])
    base.mkdir(parents=True, exist_ok=True)

    repo = GitRepo(repo_url, branch, dest_name)
    target = base / repo.dest_name

    try:
        actual_path = repo.setup()
        logger.info("Repository ready at: %s", actual_path)
        return str(actual_path)
    except Exception as e:
        logger.warning("Could not clone real repo %s (reason: %s); creating empty folder.", repo_url, e)
        # Swallow any clone/fetch errors: create an empty folder and return
        os.makedirs(target, exist_ok=True)
        return str(target)
