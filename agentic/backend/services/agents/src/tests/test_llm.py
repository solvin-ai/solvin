# tests/test_llm.py

"""
Unified test file for our LLM-driving RPC helpers:
  • run_to_completion
  • submit_to_llm

Validates simple echo and multi-step completion flows against the client_agents API.
All tests run in a repository context provided by the `test_repo` fixture.
"""

import pytest
from pprint import pformat

from shared.client_agents import (
    upsert_agent_role,
    add_running_agent,
    remove_running_agent,
    delete_agent_role,
    run_to_completion,
    add_message,
    submit_to_llm,
)

@pytest.mark.order(9)
def test_run_to_completion_echo_and_meta(test_repo):
    """
    Test run_to_completion helper with a custom echo agent.
    Verifies agent_id, status, total_time, and that the response echoes back the prompt.
    """
    repo_url = test_repo
    role = "test_ask_agent"
    description = "Agent for testing echo"
    tools = ["echo"]  # assumes an "echo" tool that repeats its input
    prompt = "You are an echo agent."

    # 1) Register the agent role
    upsert_agent_role(role=role, description=description, tools=tools, prompt=prompt)

    # 2) Spin up a running-agent instance
    agent = add_running_agent(agent_role=role, repo_url=repo_url)
    assert isinstance(agent, dict), f"Expected dict from add_running_agent, got: {agent!r}"
    agent_id = agent.get("agent_id")
    assert agent_id, "add_running_agent must return an agent_id"

    try:
        # 3) Run to completion
        user_prompt = "Please echo this back."
        result = run_to_completion(
            agent_role=role,
            user_prompt=user_prompt,
            agent_id=agent_id,
            repo_url=repo_url
        )
        assert isinstance(result, dict), f"Expected dict from run_to_completion, got: {result!r}"
        print("TEST DEBUG - echo result data:", pformat(result))

        # 4) Assertions
        assert result.get("agent_id") == agent_id
        assert result.get("status") == "success"
        total_time = result.get("total_time")
        assert isinstance(total_time, (int, float)) and total_time >= 0

        response = result.get("response", "")
        assert (
            user_prompt in response
            or "echo" in response.lower()
        ), f"Unexpected response: {response!r}"

    finally:
        # 5) Cleanup
        try:
            remove_running_agent(agent_role=role, agent_id=agent_id, repo_url=repo_url)
        except Exception as e:
            print("TEST CLEANUP ERROR (remove_running_agent):", e)
        delete_agent_role(agent_role=role)


@pytest.mark.order(10)
def test_run_to_completion_task_workflow(test_repo):
    """
    Test run_to_completion with a workflow agent:
      1) list directory tree
      2) read a file
      3) mark the task completed
    """
    repo_url = test_repo
    role = "workflow_agent"
    description = "Agent for testing a fetch/read/complete workflow"
    tools = ["directory_tree", "read_file", "set_work_completed"]
    prompt = (
        "You are a workflow agent. "
        "First list the directory tree, then read a file, then mark the task completed."
    )

    # 1) Register the agent role
    upsert_agent_role(role=role, description=description, tools=tools, prompt=prompt)

    # 2) Spin up a running-agent instance
    agent = add_running_agent(agent_role=role, repo_url=repo_url)
    assert isinstance(agent, dict), f"Expected dict from add_running_agent, got: {agent!r}"
    agent_id = agent.get("agent_id")
    assert agent_id, "add_running_agent must return an agent_id"

    try:
        # 3) Run to completion
        result = run_to_completion(
            agent_role=role,
            agent_id=agent_id,
            repo_url=repo_url,
            user_prompt="Fetch directory, read a file, then mark the task completed."
        )
        assert isinstance(result, dict), f"Expected dict from run_to_completion, got: {result!r}"
        print("TEST DEBUG - workflow result data:", pformat(result))

        # 4) Assertions
        assert result.get("agent_id") == agent_id
        assert result.get("status") == "success"
        total_time = result.get("total_time")
        assert isinstance(total_time, (int, float)) and total_time >= 0

        response = result.get("response", "")
        assert isinstance(response, str) and response.strip(), "Empty workflow response"

    finally:
        # 5) Cleanup
        try:
            remove_running_agent(agent_role=role, agent_id=agent_id, repo_url=repo_url)
        except Exception as e:
            print("TEST CLEANUP ERROR (remove_running_agent):", e)
        delete_agent_role(agent_role=role)


@pytest.mark.order(11)
def test_submit_to_llm_single_turn(test_repo):
    """
    Test submit_to_llm helper: append a user message, then get exactly one LLM turn back.
    """
    repo_url = test_repo
    role = "test_submit_agent"
    description = "Agent for testing submit_to_llm"
    tools = ["echo"]
    prompt = "You are an echo agent."

    # 1) Register the agent role
    upsert_agent_role(role=role, description=description, tools=tools, prompt=prompt)

    # 2) Spin up a running-agent instance
    agent = add_running_agent(agent_role=role, repo_url=repo_url)
    assert isinstance(agent, dict), f"Expected dict from add_running_agent, got: {agent!r}"
    agent_id = agent.get("agent_id")
    assert agent_id, "add_running_agent must return an agent_id"

    try:
        # 3) Persist a user turn without invoking LLM
        user_text = "Hello world!"
        add_message(
            agent_role=role,
            agent_id=agent_id,
            repo_url=repo_url,
            role="user",
            content=user_text
        )

        # 4) Now invoke exactly one LLM turn
        turn = submit_to_llm(agent_role=role, agent_id=agent_id, repo_url=repo_url)
        assert isinstance(turn, dict), f"Expected dict from submit_to_llm, got: {turn!r}"
        print("TEST DEBUG - submit_to_llm turn:", pformat(turn))

        # The new turn index should be 1 (turn-0 was initial seed)
        assert turn["turn_meta"].get("turn") == 1

        msgs = turn["messages"]
        # We expect an assistant or tool response
        assert "assistant" in msgs or "tool" in msgs
        content = (
            msgs.get("assistant", msgs.get("tool", {}))
                .get("raw", {})
                .get("content", "")
        )
        assert user_text in content or "echo" in content.lower()

    finally:
        # 5) Cleanup
        try:
            remove_running_agent(agent_role=role, agent_id=agent_id, repo_url=repo_url)
        except Exception as e:
            print("TEST CLEANUP ERROR (remove_running_agent):", e)
        delete_agent_role(agent_role=role)