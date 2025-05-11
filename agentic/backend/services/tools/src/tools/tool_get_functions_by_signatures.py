# tools/tool_get_functions_by_signatures.py

from shared.config import config
from shared.logger import logger

from modules.tools_safety import (
    get_repos_dir,
    get_log_dir,
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)
import os
import json
import javalang
import ast

def extract_function_text(code, start_offset):
    """
    Given the full source code and a starting offset where the function declaration begins,
    extract and return the complete function definition (signature and body).
    Java-only helper.
    """
    pos_brace = code.find('{', start_offset)
    pos_semicolon = code.find(';', start_offset)

    if pos_brace == -1 or (pos_semicolon != -1 and pos_semicolon < pos_brace):
        end_offset = pos_semicolon + 1 if pos_semicolon != -1 else len(code)
        return code[start_offset:end_offset]

    index = pos_brace
    count = 0
    while index < len(code):
        char = code[index]
        if char == '{':
            count += 1
        elif char == '}':
            count -= 1
            if count == 0:
                index += 1  # include the closing brace
                break
        index += 1

    return code[start_offset:index]

# --- Python support helpers ---

def compute_python_signature(node: ast.AST) -> str:
    """
    Turn an ast.FunctionDef or AsyncFunctionDef into a signature string,
    e.g. "def my_func(a, b=1, *args, **kwargs)".
    """
    is_async = isinstance(node, ast.AsyncFunctionDef)
    kind = "async def" if is_async else "def"
    args = node.args
    parts = []

    # positional-only (3.8+)
    for arg in getattr(args, "posonlyargs", ()):
        parts.append(arg.arg)

    # regular args with defaults
    num_defaults = len(args.defaults or ())
    for i, arg in enumerate(args.args):
        name = arg.arg
        default_index = i - (len(args.args) - num_defaults)
        if args.defaults and default_index >= 0:
            default = ast.unparse(args.defaults[default_index])
            name = f"{name}={default}"
        parts.append(name)

    # vararg
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")

    # kw-only args
    for i, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        if args.kw_defaults and args.kw_defaults[i] is not None:
            default = ast.unparse(args.kw_defaults[i])
            name = f"{name}={default}"
        parts.append(name)

    # kwargs
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    param_list = ", ".join(parts)
    return f"{kind} {node.name}({param_list})"

def find_end_by_indentation(lines, start_line):
    """
    Fallback for Python < 3.8: scan from start_line until
    we see a line whose indent is <= the def's indent.
    Returns (end_line, end_col).
    """
    base = lines[start_line-1]
    start_indent = len(base) - len(base.lstrip(' '))
    for idx in range(start_line, len(lines)):
        line = lines[idx]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent <= start_indent:
            # end right before this line
            return idx, 0
    # ran out: include entire file
    last = lines[-1]
    return len(lines), len(last)

def process_python_file(code: str):
    """
    Parse code with ast, return a map:
      signature -> (start_offset, end_offset)
    """
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    function_map = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = compute_python_signature(node)
            # start offset
            sl, sc = node.lineno, node.col_offset
            start_offset = sum(len(lines[i]) for i in range(sl-1)) + sc
            # end offset
            if hasattr(node, "end_lineno") and hasattr(node, "end_col_offset"):
                el, ec = node.end_lineno, node.end_col_offset
            else:
                el, ec = find_end_by_indentation(lines, sl)
            end_offset = sum(len(lines[i]) for i in range(el-1)) + ec
            function_map[sig] = (start_offset, end_offset)

    return function_map

# --- end Python helpers ---

def tool_get_functions_by_signatures(requests: list) -> dict:
    repo = config["REPO_NAME"]
    repo_root = get_repo_path(repo)

    # group by file
    grouped_requests = {}
    for item in requests:
        fp = item.get("file_path"); sig = item.get("signature")
        if not fp or not sig:
            logger.error(f"Invalid request tuple: {item}")
            continue
        grouped_requests.setdefault(fp, []).append(sig)

    final_result = {}

    for orig_fp, sig_list in grouped_requests.items():
        try:
            safe_fp = resolve_repo_path(repo, orig_fp)
            check_path(repo_root, safe_fp)
        except Exception as e:
            msg = f"Error resolving file path {mask_output(orig_fp)}: {e}"
            final_result[orig_fp] = {s: msg for s in sig_list}
            continue

        if not os.path.isfile(safe_fp):
            final_result[safe_fp] = {s: f"File not found: {mask_output(safe_fp)}"
                                     for s in sig_list}
            continue

        try:
            with open(safe_fp, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            final_result[safe_fp] = {s: f"Error reading file: {e}" for s in sig_list}
            continue

        # Branch on extension
        if safe_fp.endswith(".py"):
            try:
                function_map = process_python_file(code)
            except Exception as e:
                final_result[safe_fp] = {
                    s: f"Error parsing Python file: {e}" for s in sig_list
                }
                continue
        else:
            # Java branch
            try:
                tree = javalang.parse.parse(code)
            except Exception as e:
                logger.error(f"Failed to parse Java file {mask_output(safe_fp)}: {e}")
                final_result[safe_fp] = {
                    s: f"Error parsing Java file: {e}" for s in sig_list
                }
                continue

            function_map = {}

            def compute_method_signature(node):
                modifier_str = " ".join(sorted(node.modifiers)) if node.modifiers else ""
                param_list = []
                for param in node.parameters:
                    t = param.type
                    if hasattr(t, "name"):
                        type_name = t.name
                    else:
                        type_name = str(t)
                    if getattr(t, "dimensions", None):
                        type_name += "[]" * len(t.dimensions)
                    param_list.append(f"{type_name} {param.name}")
                params = ", ".join(param_list)
                if isinstance(node, javalang.tree.MethodDeclaration):
                    rt = ""
                    if node.return_type:
                        rt = (node.return_type.name
                              if hasattr(node.return_type, "name")
                              else str(node.return_type))
                    sig = f"{modifier_str} {rt} {node.name}({params})".strip()
                else:
                    sig = f"{modifier_str} {node.name}({params})".strip()
                return sig

            def process_type(type_decl):
                for _, node in type_decl.filter(
                        (javalang.tree.MethodDeclaration,
                         javalang.tree.ConstructorDeclaration)):
                    sig = compute_method_signature(node)
                    if node.position:
                        sl, sc = node.position
                        lines = code.splitlines(keepends=True)
                        offset = sum(len(lines[i]) for i in range(sl-1)) + (sc-1)
                        function_map[sig] = offset
                # recurse into inner types
                for inner in getattr(type_decl, "body", []):
                    if isinstance(inner, (
                        javalang.tree.ClassDeclaration,
                        javalang.tree.InterfaceDeclaration,
                        javalang.tree.EnumDeclaration
                    )):
                        process_type(inner)

            for type_decl in tree.types:
                process_type(type_decl)

        # Extract requested snippets
        file_result = {}
        for req_sig in sig_list:
            if req_sig in function_map:
                if safe_fp.endswith(".py"):
                    start, end = function_map[req_sig]
                    snippet = code[start:end]
                else:
                    snippet = extract_function_text(code, function_map[req_sig])
                file_result[req_sig] = mask_output(snippet)
            else:
                file_result[req_sig] = (
                    f"Function signature not found in {mask_output(safe_fp)}"
                )
        final_result[safe_fp] = file_result

    return {"success": True, "output": final_result}

def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_get_functions_by_signatures",
            "description": (
                "Parses Java (.java) or Python (.py) files and for each tuple in the provided "
                "'requests' array ({file_path, signature}) returns the complete function "
                "(signature + body)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requests": {
                        "type": "array",
                        "description": "List of tuples each containing a 'file_path' and 'signature'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "Relative path to the source file."
                                },
                                "signature": {
                                    "type": "string",
                                    "description": "Function signature to extract."
                                }
                            },
                            "required": ["file_path", "signature"],
                            "additionalProperties": False,
                            "strict": True
                        }
                    }
                },
                "required": ["requests"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-update",
            "type": "readonly"
        }
    }
