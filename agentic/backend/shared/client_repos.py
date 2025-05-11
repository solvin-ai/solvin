# shared/client_repos.py

import requests
from requests.exceptions import ReadTimeout
from typing import Optional, Dict, Any, List, Union
from shared.config import config

# Base service URL + API prefix
SERVICE_URL_REPOS = config.get("SERVICE_URL_REPOS", "").rstrip("/")
API_VERSION       = "v1"
API_PREFIX        = f"/api/{API_VERSION}"
DEFAULT_HEADERS   = {"Content-Type": "application/json"}
# Default for all non‐blocking calls (in seconds)
DEFAULT_TIMEOUT   = 10


class ReposClientError(Exception):
    """Base exception for ReposClient HTTP errors."""
    # We'll attach `response` dynamically when we raise this.


class ReposClientConflict(ReposClientError):
    """Raised when the API returns HTTP 409 Conflict."""
    # We'll attach `response` dynamically when we raise this.


class ReposClient:
    def __init__(
        self,
        api_url: Optional[str]                 = None,
        headers: Optional[Dict[str, str]]      = None,
        timeout: Optional[Union[float, tuple]] = None,
    ):
        """
        api_url:    override the host (e.g. "http://localhost:8002"). We still append /api/v1.
        headers:    merge/override the default JSON headers.
        timeout:    for non‐blocking calls, either a float (seconds) or a (connect, read) tuple.
        """
        base = api_url.rstrip("/") if api_url else SERVICE_URL_REPOS
        self.base_url = f"{base}{API_PREFIX}"
        self.session  = requests.Session()
        self.headers  = {**DEFAULT_HEADERS, **(headers or {})}
        self.timeout  = timeout if timeout is not None else DEFAULT_TIMEOUT

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Internal helper: raises ReposClientConflict on 409 or ReposClientError on other 4xx/5xx.
        If you pass a `timeout=` keyword here it will override self.timeout.
        """
        url = f"{self.base_url}{path}"

        # pull out any per‐call override
        override = kwargs.pop("timeout", None)
        used_to = override if override is not None else self.timeout

        # build a (connect, read) tuple if they gave us just a number
        if isinstance(used_to, (int, float)):
            connect_to = 3.0
            read_to    = float(used_to) + 5.0
            http_to    = (connect_to, read_to)
        else:
            # assume they already gave us (connect, read)
            http_to = used_to

        resp = self.session.request(
            method=method,
            url=url,
            headers=self.headers,
            timeout=http_to,
            **kwargs
        )

        # 409 Conflict → ReposClientConflict
        if resp.status_code == 409:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            exc = ReposClientConflict(f"{resp.status_code} Conflict: {detail}")
            exc.response = resp
            raise exc

        # any other 4xx/5xx → ReposClientError
        try:
            resp.raise_for_status()
        except requests.HTTPError as http_err:
            exc = ReposClientError(f"{method} {url} → {resp.status_code}: {resp.text}")
            exc.response = resp
            raise exc from http_err

        return resp

    # Root & health endpoints
    def root(self) -> Dict[str, Any]:
        return self._request("GET", "/").json()

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health").json()

    def ready(self) -> Dict[str, Any]:
        return self._request("GET", "/ready").json()

    def status(self) -> Dict[str, Any]:
        return self._request("GET", "/status").json()

    # Repository info
    def list_repos(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/repos/list").json()

    def get_repo_info(self, repo_url: str) -> Dict[str, Any]:
        return self._request("GET", "/repos/info", params={"repo_url": repo_url}).json()

    def info_bulk(self, repo_urls: List[str]) -> List[Dict[str, Any]]:
        return self._request("POST", "/repos/info_bulk", json={"repo_urls": repo_urls}).json()

    # URL‐based admit
    def admit_repo(
        self,
        repo_url: str,
        team_id: Optional[str]        = None,
        priority: int                 = 0,
        default_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = {
            "repo_url":       repo_url,
            "team_id":        team_id,
            "priority":       priority,
            "default_branch": default_branch,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return self._request("POST", "/repos/admit", json=payload).json()

    def admit_bulk(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._request("POST", "/repos/admit_bulk", json={"repos": repos}).json()

    # Raw‐columns add
    def add_repo(
        self,
        repo_url: str,
        repo_name: str,
        repo_owner: str,
        team_id: str,
        priority: int,
        metadata: Dict[str, Any],
        customer_id: Optional[str]    = None,
        default_branch: Optional[str] = None,
        jdk_version: Optional[str]    = None
    ) -> Dict[str, Any]:
        payload = {
            "repo_url":       repo_url,
            "repo_name":      repo_name,
            "repo_owner":     repo_owner,
            "customer_id":    customer_id,
            "team_id":        team_id,
            "default_branch": default_branch,
            "priority":       priority,
            "metadata":       metadata,
            "jdk_version":    jdk_version,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return self._request("POST", "/repos/add", json=payload).json()

    def add_bulk(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._request("POST", "/repos/add_bulk", json={"repos": repos}).json()

    # Claim endpoints
    def claim_repo(self, ttl: int = 60) -> Dict[str, Any]:
        return self._request("POST", "/repos/claim", params={"ttl": ttl}).json()

    def claim_repo_blocking(self, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Try to block‐claim a repo for up to `timeout` seconds.
        On success you get back the claimed record.
        On any 4xx/5xx (including 404 if the server times out) we raise
        the usual ReposClientError or ReposClientConflict.
        """
        try:
            return self._request(
                "POST",
                "/repos/claim_blocking",
                params={"timeout": timeout},
                timeout=(3.0, timeout + 5.0),
            ).json()
        except ReadTimeout as e:
            # no repo became available before our read‐timeout → treat like 404
            resp_404 = requests.Response()
            resp_404.status_code = 404
            exc = ReposClientError("Blocking claim timed out (no repo available)")
            exc.response = resp_404
            raise exc from e

    # Complete endpoints
    def complete_repo(self, repo_url: str) -> Dict[str, Any]:
        return self._request("POST", "/repos/complete", json={"repo_url": repo_url}).json()

    def complete_bulk(self, repo_urls: List[str]) -> List[Dict[str, Any]]:
        payload = {"repos": [{"repo_url": url} for url in repo_urls]}
        return self._request("POST", "/repos/complete_bulk", json=payload).json()

    # Delete endpoint
    def delete_repo(self, repo_url: str, remove_db: bool = True) -> Dict[str, Any]:
        payload = {"repo_url": repo_url, "remove_db": remove_db}
        return self._request("DELETE", "/repos/delete", json=payload).json()


if __name__ == "__main__":
    client = ReposClient()
    print("Root   →", client.root())
    print("Health →", client.health())
    print("Ready  →", client.ready())
    print("Status →", client.status())
    print("List   →", client.list_repos())
