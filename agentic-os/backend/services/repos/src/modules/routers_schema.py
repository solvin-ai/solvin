# modules/routers_schema.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Repo(BaseModel):
    repo_url:          str
    repo_name:         Optional[str]        = None
    repo_owner:        str
    team_id:           str
    default_branch:    Optional[str]        = None
    priority:          Optional[int]        = 0

    # First-class metadata now stored as real columns:
    source_file_count: int                  = 0
    total_loc:         int                  = 0
    language:          Optional[str]        = None

    # The remaining ancillary data:
    metadata:          Optional[Dict[str, Any]] = None
    jdk_version:       Optional[str]            = None
    repo_path:         Optional[str]            = None


class RepoClaimResponse(BaseModel):
    repo_url:       str
    repo_owner:     str
    repo_name:      str
    default_branch: str
    priority:       int


class RepoAdmitByUrlRequest(BaseModel):
    repo_url:       str
    team_id:        str
    priority:       int                   = 0
    default_branch: Optional[str]         = None


class BulkRepoAdmitByUrlRequest(BaseModel):
    repos: List[RepoAdmitByUrlRequest]


class RepoAddRequest(BaseModel):
    repo_url:       str
    repo_name:      str
    repo_owner:     str
    customer_id:    Optional[str]         = None
    team_id:        str
    default_branch: Optional[str]         = None
    priority:       int                   = 0
    metadata:       Dict[str, Any]
    jdk_version:    Optional[str]         = None


class BulkRepoAddRequest(BaseModel):
    repos: List[RepoAddRequest]


class RepoCompleteRequest(BaseModel):
    repo_url: str


class BulkRepoCompleteRequest(BaseModel):
    repos: List[RepoCompleteRequest]


class BulkRepoInfoRequest(BaseModel):
    repo_urls: List[str]


class RepoDeleteRequest(BaseModel):
    repo_url:   str
    remove_db:  bool = True
