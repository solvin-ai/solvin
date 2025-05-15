# tests/test_execute_bulk.py

import json
import pytest
from shared.client_tools import execute_bulk

def test_bulk_read_file_and_directory_tree(fake_local_repo):
    """
    1) Call read_file on the fake README (sandboxed → not_found).
    2) Call directory_tree on “.” (sandboxed → failure).
    """
    repo_url   = fake_local_repo["repo_url"]
    repo_name  = fake_local_repo["repo_name"]
    repo_owner = fake_local_repo["repo_owner"]

    req1 = {
        "tool_name":   "read_file",
        "input_args":  {"file_path": "README"},
        "repo_url":    repo_url,
        "repo_name":   repo_name,
        "repo_owner":  repo_owner,
        "metadata":    {},
    }
    req2 = {
        "tool_name":   "directory_tree",
        "input_args":  {"path": "."},
        "repo_url":    repo_url,
        "repo_name":   repo_name,
        "repo_owner":  repo_owner,
        "metadata":    {},
    }

    results = execute_bulk([req1, req2])
    assert isinstance(results, list)
    assert len(results) == 2

    # --- 1) read_file → returns a not_found JSON in output ---
    read_item = results[0]
    assert read_item["status"] == "ok"
    exec1 = read_item["result"]
    assert exec1["status"] == "success"
    resp1 = exec1["response"]
    data1 = json.loads(resp1["output"])
    assert data1["status"] == "not_found"
    assert "does not exist" in data1["message"]

    # --- 2) directory_tree → under our sandbox it fails ---
    tree_item = results[1]
    assert tree_item["status"] == "ok"
    exec2 = tree_item["result"]
    assert exec2["status"] == "failure"
    resp2 = exec2["response"]
    # The tool reports success=False on error, and puts its error text in "output"
    assert resp2.get("success") is False
    assert isinstance(resp2["output"], str)

def test_bulk_invalid_transport_error():
    # malformed request → HTTP/client error
    with pytest.raises(Exception):
        execute_bulk([{"foo": "bar"}])
