# tools/tool_fetch_github_issues.py

from shared.config import config
from modules.tools_safety import (
    get_repos_dir,
    get_log_dir,
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)

"""
This tool fetches GitHub issues from a repository using the GitHub API,
applying server-side filtering (state, milestone, labels, assignee, mentioned, since)
and client-side boosting (preferred assignee/mentioned text and priority labels).
It then returns a JSON‐structured summary of each issue. Each issue is keyed by its
issue number and includes:
  • title
  • body
  • comments (an array of comment texts fetched from the issue’s "comments_url")
  • users (an array combining the issue’s user and the users from all comments)

Note:
  - The repository owner (REPO_OWNER) and the repository name (REPO_NAME) are obtained from configuration.
  - The API base URL and the GitHub token are taken from config (API_URL_GITHUB and API_TOKEN_GITHUB).
  - For public repositories (determined via an API call), the token is not provided.
Intended for use as an OpenAI function-call tool.
"""

import requests
from requests.exceptions import HTTPError
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from shared.logger import logger

logger = logger


def _load_repo_config():
    owner = config.get("REPO_OWNER")
    if not owner:
        raise EnvironmentError("REPO_OWNER must be set in the configuration.")
    repo = config.get("REPO_NAME")
    if not repo:
        raise EnvironmentError("REPO_NAME must be set in the configuration.")
    token = config.get("API_TOKEN_GITHUB")
    if not token:
        raise EnvironmentError("API_TOKEN_GITHUB must be set in the configuration.")
    api_url = config.get("API_URL_GITHUB", "https://api.github.com/")
    return owner, repo, token, api_url


def is_public_repo(owner: str, repo: str, api_url_github: str) -> bool:
    """
    Determine whether the specified repository is public.
    Makes a GET request to the repository's API URL and inspects the 'private'
    field. Returns True if the repository is public (i.e. "private": false),
    and False otherwise. A 404 response is treated as 'private' (no error).
    """
    details_url = f"{api_url_github.rstrip('/')}/repos/{owner}/{repo}"
    try:
        response = requests.get(details_url)
        if response.status_code == 404:
            logger.info(
                "Repository %s/%s not found (404); treating as private.",
                owner, repo
            )
            return False
        response.raise_for_status()
        data = response.json()
        return data.get("private", True) is False
    except HTTPError as e:
        logger.error(
            "HTTP error checking if repository %s/%s is public: %s",
            owner, repo, e
        )
        return False
    except Exception as e:
        logger.error(
            "Error checking if repository %s/%s is public: %s",
            owner, repo, e
        )
        return False


def fetch_all_issues(
    owner: str,
    repo: str,
    api_url_github: str,
    token: Optional[str] = None,
    state: str = "open",
    milestone: Optional[str] = None,
    search_labels: Optional[str] = None,
    filter_assignee: Optional[str] = None,
    filter_mentioned: Optional[str] = None,
    since: Optional[str] = None,
    per_page: int = 10,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve GitHub issues from a repository with optional filtering and pagination.
    """
    issues: List[Dict[str, Any]] = []
    page = 1
    session = requests.Session()
    if token:
        session.headers.update({"Authorization": f"token {token}"})
    else:
        logger.info("No GitHub token provided (or necessary).")

    params = {
        "state": state,
        "sort": "created",
        "direction": "desc",
        "per_page": per_page,
        "page": page,
    }
    if milestone:
        params["milestone"] = milestone
    if search_labels:
        params["labels"] = search_labels
    if filter_assignee:
        params["assignee"] = filter_assignee
    if filter_mentioned:
        params["mentioned"] = filter_mentioned
    if since:
        params["since"] = since

    base_url = api_url_github.rstrip("/")
    issues_url = f"{base_url}/repos/{owner}/{repo}/issues"

    while True:
        logger.debug(f"Fetching page {page} from {issues_url} with parameters: {params}")
        try:
            resp = session.get(issues_url, params=params)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            if resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining", "0")
                logger.error(
                    f"HTTP 403: Access forbidden or rate limit exceeded "
                    f"(remaining: {remaining}). Error: {http_err}"
                )
            else:
                logger.error(f"HTTP error on page {page}: {http_err}")
            break
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error on page {page}: {req_err}")
            break

        try:
            batch = resp.json()
        except ValueError as json_err:
            logger.error(f"Error decoding JSON on page {page}: {json_err}")
            break

        if not isinstance(batch, list):
            logger.error("Unexpected response format. Exiting.")
            break

        issues.extend(batch)
        if len(batch) < per_page:
            break

        page += 1
        if max_pages and page > max_pages:
            logger.info("Reached max_pages limit (%d).", max_pages)
            break
        params["page"] = page

    logger.info("Total issues fetched: %d", len(issues))
    return issues


def filter_pull_requests(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove pull requests from the issues list (since GitHub returns pull requests on this endpoint).
    """
    return [issue for issue in issues if "pull_request" not in issue]


def parse_date(date_str: Optional[str]) -> datetime:
    """
    Convert an ISO 8601 date string to a datetime object.
    Returns a minimal datetime if parsing fails.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ") if date_str else datetime.min
    except (ValueError, TypeError):
        return datetime.min


def compute_priority(
    issue: Dict[str, Any],
    preferred_assignee: str,
    preferred_mentioned: str,
    boost_labels: List[str],
) -> int:
    """
    Compute a composite priority score:
      • 3 if the issue is assigned to the preferred_assignee.
      • 2 if the title or body contains the preferred_mentioned text.
      • 1 if any label from boost_labels is present.
      • 0 otherwise.
    """
    assignee = issue.get("assignee")
    if assignee and assignee.get("login", "").strip().lower() == preferred_assignee.lower():
        return 3

    text = f"{issue.get('title', '')} {issue.get('body', '')}".lower()
    if preferred_mentioned.lower() in text:
        return 2

    issue_labels = [label.get("name", "").strip().lower() for label in issue.get("labels", [])]
    for label in boost_labels:
        if label in issue_labels:
            return 1

    return 0


def custom_sort_issues(
    issues: List[Dict[str, Any]],
    preferred_assignee: str,
    preferred_mentioned: str,
    boost_labels: List[str],
) -> List[Dict[str, Any]]:
    """
    Sort issues using a composite key.
    """
    def sort_key(issue: Dict[str, Any]) -> Tuple[int, datetime, datetime, int]:
        priority = compute_priority(issue, preferred_assignee, preferred_mentioned, boost_labels)
        created = parse_date(issue.get("created_at"))
        updated = parse_date(issue.get("updated_at"))
        comments = issue.get("comments", 0)
        return (priority, created, updated, comments)

    return sorted(issues, key=sort_key, reverse=True)


def fetch_comments(comments_url: str, token: Optional[str]) -> Tuple[List[str], List[str]]:
    """
    Fetch a list of comment texts and the corresponding comment user logins
    from an issue's comments_url.
    Returns:
      A tuple with two lists:
        - The first list contains the "body" text for each comment.
        - The second list contains the corresponding user login from each comment.
    """
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        response = requests.get(comments_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        comment_bodies: List[str] = []
        comment_users: List[str] = []
        if isinstance(data, list):
            for comment in data:
                comment_body = comment.get("body", "").strip()
                comment_bodies.append(comment_body)
                user_obj = comment.get("user", {})
                login = user_obj.get("login")
                if login:
                    comment_users.append(login)
        return comment_bodies, comment_users
    except Exception as e:
        logger.error("Error fetching comments from %s: %s", comments_url, e)
        return [], []


def format_issues_as_json(issues: List[Dict[str, Any]], token: Optional[str]) -> Dict[str, Any]:
    """
    Create a JSON-structured result for the list of issues.

    The returned dictionary contains an "issues" key mapping to another dictionary.
    Each key in that dictionary is the stringified issue number, which maps to an object
    with:
      • title
      • body
      • comments (an array of comment texts)
      • users (an array of user logins from the issue and its comments)
    """
    output: Dict[str, Any] = {}
    for issue in issues:
        issue_number = issue.get("number")
        if issue_number is None:
            continue
        title = issue.get("title", "No Title")
        body = issue.get("body", "No description available.")
        comments_url = issue.get("comments_url", "")
        comment_bodies, comment_users = ([], []) if not comments_url else fetch_comments(comments_url, token)
        users_set = set()
        issue_user = issue.get("user", {}).get("login")
        if issue_user:
            users_set.add(issue_user)
        users_set.update(comment_users)
        users_list = sorted(users_set)

        output[str(issue_number)] = {
            "title": title,
            "body": body,
            "comments": comment_bodies,
            "users": users_list,
        }

    return {"issues": output}


def tool_fetch_github_issues(**params) -> Dict[str, Any]:
    """
    Tool entrypoint for fetching GitHub issues.
    This tool no longer accepts a repository name as an input parameter.
    It always uses the repository name from configuration (REPO_NAME).

    Expected keyword arguments:
      - state (string, optional): Issue state ("open", "closed", or "all"). Default: "open"
      - milestone (string, optional): Filter issues by milestone.
      - search_labels (string, optional): Comma-separated labels for server-side filtering.
      - filter_assignee (string, optional): Filter issues assigned to a specific user.
      - filter_mentioned (string, optional): Filter issues mentioning a specific user.
      - since (string, optional): ISO8601 timestamp to filter issues on/after.
      - max_pages (integer, optional): Limit the number of pages to fetch. Default: 1
      - per_page (integer, optional): Number of issues per page to fetch. Default: 10
      - preferred_assignee (string, optional): Preferred assignee for boosting. Default: "Solvin"
      - preferred_mentioned (string, optional): Preferred text for boosting in title/body. Default: "Solvin"
      - filter_labels (string, optional): Comma-separated labels for priority boost. Default: "critical,high"

    Returns:
      A dictionary with keys:
         - "success": Boolean indicating success.
         - "output": A JSON object with each issue keyed by its number containing its title, body, comments, and users.
    """
    # sandbox safety: ensure the configured repo actually lives under our repos dir
    repo = config["REPO_NAME"]
    repo_root = check_path(get_repo_path(repo), allowed_root=get_repos_dir())

    try:
        owner, repo, token, api_url_github = _load_repo_config()
    except Exception as e:
        logger.exception("Configuration error for tool_fetch_github_issues")
        return {"success": False, "output": mask_output(str(e))}

    state = params.get("state", "open")
    milestone = params.get("milestone")
    search_labels = params.get("search_labels", "")
    filter_assignee = params.get("filter_assignee")
    filter_mentioned = params.get("filter_mentioned")
    since = params.get("since")
    max_pages = params.get("max_pages", 1)
    per_page = params.get("per_page", 10)

    if is_public_repo(owner, repo, api_url_github):
        logger.info("Repository %s/%s is public. Not using authentication token.", owner, repo)
        token = None

    preferred_assignee = params.get("preferred_assignee", "Solvin")
    preferred_mentioned = params.get("preferred_mentioned", "Solvin")
    filter_labels_str = params.get("filter_labels", "critical,high")
    boost_labels = [label.strip().lower() for label in filter_labels_str.split(",") if label.strip()]

    try:
        issues = fetch_all_issues(
            owner=owner,
            repo=repo,
            api_url_github=api_url_github,
            token=token,
            state=state,
            milestone=milestone,
            search_labels=search_labels,
            filter_assignee=filter_assignee,
            filter_mentioned=filter_mentioned,
            since=since,
            per_page=per_page,
            max_pages=max_pages,
        )

        if not issues:
            return {"success": True, "output": {"issues": {}}}

        issues = filter_pull_requests(issues)
        sorted_issues = custom_sort_issues(issues, preferred_assignee, preferred_mentioned, boost_labels)
        json_output = format_issues_as_json(sorted_issues, token)
        return {"success": True, "output": json_output}
    except Exception as e:
        logger.exception("Error fetching or processing GitHub issues")
        return {"success": False, "output": mask_output(str(e))}


def get_tool() -> Dict[str, Any]:
    """
    Returns the tool specification for the GitHub issues fetching tool, following the OpenAI function-call schema.
    Note:
      - The repository name is no longer an input parameter but is taken from REPO_NAME in configuration.
      - Repository owner is taken from REPO_OWNER.
      - The API base URL is set via API_URL_GITHUB.
      - The output is a JSON object where each issue is keyed by its number and contains its title, body, comments, and users.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_fetch_github_issues",
            "description": (
                "Fetches GitHub issues from a repository using the GitHub API with support for server-side filtering "
                "(state, milestone, search_labels, filter_assignee, filter_mentioned, since) and client-side boosting "
                "(preferred assignee/mentioned text and priority boost labels). "
                "This tool always uses the repository name from configuration (REPO_NAME) and the repository owner from REPO_OWNER. "
                "The output is a JSON object with each issue keyed by its number containing its title, body, fetched comment texts, "
                "and an array of user login names aggregated from the issue and its comments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Issue state ('open', 'closed', or 'all')",
                        "default": "open",
                    },
                    "milestone": {
                        "type": "string",
                        "description": "Filter issues by milestone (number, 'none', or '*')",
                    },
                    "search_labels": {
                        "type": "string",
                        "description": "Comma-separated labels for server-side filtering (e.g., 'bug,enhancement')",
                        "default": "",
                    },
                    "filter_assignee": {
                        "type": "string",
                        "description": "Filter issues assigned to a specific user",
                    },
                    "filter_mentioned": {
                        "type": "string",
                        "description": "Filter issues mentioning a specific user",
                    },
                    "since": {
                        "type": "string",
                        "description": "ISO8601 timestamp to filter issues updated on/after (e.g., '2023-01-01T00:00:00Z')",
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "Limit the number of pages to fetch",
                        "default": 1,
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Number of issues per page to fetch",
                        "default": 10,
                    },
                    "preferred_assignee": {
                        "type": "string",
                        "description": "Preferred assignee to boost ranking",
                        "default": "Solvin",
                    },
                    "preferred_mentioned": {
                        "type": "string",
                        "description": "Preferred text to boost ranking in title/body",
                        "default": "Solvin",
                    },
                    "filter_labels": {
                        "type": "string",
                        "description": "Comma-separated labels for priority boost (default: 'critical,high')",
                        "default": "critical,high",
                    },
                },
                "required": [],
                "additionalProperties": False,
                "strict": True,
            },
        },
        "internal": {
            "preservation_policy": "one-of",
            "type": "readonly",
        },
    }


if __name__ == "__main__":
    test_params = {
        "state": "open",
        "milestone": None,
        "search_labels": "bug",
        "filter_assignee": None,
        "filter_mentioned": None,
        "since": None,
        "max_pages": 1,
        "per_page": 10,
        "preferred_assignee": "Solvin",
        "preferred_mentioned": "Solvin",
        "filter_labels": "critical,high",
    }
    result = tool_fetch_github_issues(**test_params)
    import json
    print(json.dumps(result, indent=2))
