# tests/test_tools_info.py

import pytest
from shared.client_tools import tools_info, tools_list as fetch_tools_list, ToolError

@pytest.fixture
def tools_list():
    # fetch_tools_list() calls the client function tools_list()
    return fetch_tools_list()

def test_tools_info_single(tools_list):
    if not tools_list:
        pytest.skip("no tools to query")
    name = tools_list[0]["tool_name"]
    info = tools_info(tool_name=name)
    assert isinstance(info, dict)

def test_tools_info_bulk(tools_list):
    names = [t["tool_name"] for t in tools_list]
    bulk = tools_info(tool_names=names, meta=True, schema=True)
    assert isinstance(bulk, dict)
    assert set(bulk.keys()) == set(names)

def test_tools_info_flags(tools_list):
    name = tools_list[0]["tool_name"]
    assert isinstance(tools_info(tool_name=name, meta=True,  schema=False), dict)
    assert isinstance(tools_info(tool_name=name, meta=False, schema=True), dict)
    neither = tools_info(tool_name=name, meta=False, schema=False)
    assert isinstance(neither, dict) and not neither

def test_tools_info_no_args():
    with pytest.raises(ValueError):
        tools_info()

def test_tools_info_not_found():
    with pytest.raises(ToolError):
        tools_info(tool_name="no_such_tool_xyz")