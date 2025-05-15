# tests/test_running_errors.py

import pytest

from shared.client_agents import (
    list_running_agents,
    get_current_running_agent,
    add_running_agent,
    remove_running_agent,
    set_current_agent,
)

@pytest.mark.parametrize(
    "func,args,errmsg",
    [
        # list_running_agents: missing repo_url
        (list_running_agents,  {"repo_url": ""}, "repo_url is required"),
        # get_current_running_agent: missing repo_url
        (get_current_running_agent, {"repo_url": ""}, "repo_url is required"),
        # add_running_agent: missing repo_url
        (add_running_agent,     {"agent_role": "role", "repo_url": ""}, "repo_url is required"),
        # remove_running_agent: missing repo_url
        (remove_running_agent,  {"agent_role": "role", "agent_id": "id", "repo_url": ""}, "repo_url is required"),
        # set_current_agent: missing repo_url
        (set_current_agent,     {"agent_role": "role", "agent_id": "id", "repo_url": ""}, "repo_url is required"),
    ]
)
def test_running_agent_parameter_validation(func, args, errmsg):
    """
    Each of the client_agents functions that requires both repo_url
    should raise a ValueError if either is missing or empty.
    """
    with pytest.raises(ValueError) as excinfo:
        func(**args)
    # The exception message should mention the missing parameter
    assert errmsg in str(excinfo.value)
