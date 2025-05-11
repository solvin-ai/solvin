# modules/tools_executor.py

import time
import json
from modules.logs import logger

def execute_tool(tool_name, input_args, registry=None, turn_id=None):
    """
    Executes a tool by its name using the provided unified tools registry.
    
    Parameters:
      tool_name (str): The name of the tool to execute.
      input_args (dict): Input arguments for the tool.
      registry (dict, optional): A unified tools registry. If not provided, it is retrieved via get_global_registry().
      turn_id (Any, optional): An optional turn identifier added to input arguments.
    
    Returns:
      dict: A dictionary containing:
            - "execution_time": The time (in seconds) taken to execute the tool.
            - "status": "success" or "failure".
            - "error": A string describing the error if any.
            - "response": The tool's raw output as a dictionary.
    """
    if registry is None:
        try:
            from modules.tools_registry import get_global_registry
            registry = get_global_registry()
        except Exception as e:
            error_msg = f"Global tools registry could not be retrieved: {e}"
            logger.error(error_msg)
            return {"execution_time": 0.0, "status": "failure", "error": error_msg, "response": {}}
    
    tool_record = registry.get(tool_name)
    if not tool_record:
        error_msg = f"Tool '{tool_name}' is not available in the registry."
        logger.error(error_msg)
        return {"execution_time": 0.0, "status": "failure", "error": error_msg, "response": {}}
    
    executor = tool_record.get("executor")
    if not callable(executor):
        error_msg = f"Executor for tool '{tool_name}' is not callable."
        logger.error(error_msg)
        return {"execution_time": 0.0, "status": "failure", "error": error_msg, "response": {}}
    
    if turn_id is not None:
        input_args["turn_id"] = turn_id
    
    logger.info("Executing tool '%s' with args: %s", tool_name, input_args)
    start_time = time.time()
    try:
        result = executor(_execution=True, **input_args)
        elapsed = time.time() - start_time
    except Exception as ex:
        error_msg = f"Tool '{tool_name}' execution error: {ex}"
        logger.error(error_msg)
        elapsed = time.time() - start_time
        return {"execution_time": elapsed, "status": "failure", "error": error_msg, "response": {}}
    
    if isinstance(result, str):
        try:
            result_json = json.loads(result)
        except Exception as e:
            error_msg = f"Tool '{tool_name}' returned non-JSON response: {result}"
            logger.error(error_msg)
            return {"execution_time": elapsed, "status": "failure", "error": error_msg, "response": {}}
    elif isinstance(result, dict):
        result_json = result
    else:
        error_msg = f"Tool '{tool_name}' returned an unrecognized type: {type(result)}"
        logger.error(error_msg)
        return {"execution_time": elapsed, "status": "failure", "error": error_msg, "response": {}}
    
    # Determine the overall status using the tool's returned "success" flag.
    status = "success" if result_json.get("success", False) else "failure"
    error_msg = "" if status == "success" else result_json.get("error", "")
    
    logger.info("Tool: '%s' | Time: %.4f sec | Status: %s | Error: %s | Result: %s", tool_name, elapsed, status, error_msg, result_json)
    return {"execution_time": elapsed, "status": status, "error": error_msg, "response": result_json}

if __name__ == "__main__":
    # Dummy executor function to simulate tool behavior.
    def dummy_executor(_execution=False, **kwargs):
        # Simulate processing and return a JSON-string result.
        return json.dumps({"success": True, "output": f"Processed args: {kwargs}"})
    
    # Dummy registry for testing.
    dummy_registry = {
        "dummy_tool": {
            "executor": dummy_executor
        }
    }
    
    # Execute the dummy tool.
    test_result = execute_tool("dummy_tool", {"param": "value"}, registry=dummy_registry, turn_id=1)
    print("Test tool execution result:")
    print(json.dumps(test_result, indent=2))
