# tools/tool_get_code_structure.py

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
Parses one or more Java or Python files to list all interfaces (Java), classes,
methods, global variables, and imports. Additionally, for each type
(class/interface/enum in Java; class in Python), it collects its public methods.
Uses javalang for Java and the built-in ast module for Python.
"""

import os
import javalang
import ast

from shared.logger import logger
logger = logger


def tool_get_code_structure(file_paths: list) -> dict:
    # determine the repo root inside the sandbox
    repo = config["REPO_NAME"]
    repo_root = get_repo_path(repo)

    overall_success = True
    result = {}

    for orig_file_path in file_paths:
        # resolve & validate the user‐supplied path
        try:
            safe_file_path = resolve_repo_path(repo, orig_file_path)
        except Exception as e:
            result[orig_file_path] = f"Error resolving path: {mask_output(str(e))}"
            overall_success = False
            continue

        logger.debug(
            f"[tool_get_code_structure] Resolved safe path: '{safe_file_path}' "
            f"from '{orig_file_path}' (cwd='{os.getcwd()}')"
        )

        if not os.path.isfile(safe_file_path):
            result[orig_file_path] = f"File not found: {mask_output(safe_file_path)}"
            overall_success = False
            continue

        # read the source code
        try:
            with open(safe_file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            result[orig_file_path] = (
                f"Error reading file {mask_output(safe_file_path)}: "
                f"{mask_output(str(e))}"
            )
            overall_success = False
            continue

        # dispatch by file extension
        ext = os.path.splitext(safe_file_path)[1].lower()
        if ext == ".java":
            # --- Java parsing using javalang ---
            try:
                tree = javalang.parse.parse(code)
            except Exception as e:
                result[orig_file_path] = (
                    f"Error parsing Java file {mask_output(safe_file_path)}: "
                    f"{mask_output(str(e))}"
                )
                overall_success = False
                continue

            # collect imports
            imports_list = []
            for imp in getattr(tree, "imports", []):
                imp_str = "import "
                if imp.static:
                    imp_str += "static "
                imp_str += imp.path
                if imp.wildcard:
                    imp_str += ".*"
                imp_str += ";"
                imports_list.append(imp_str)

            interfaces = []
            classes = []
            methods = []
            global_vars = []
            public_methods_by_type = {}

            # helper to recurse through Java types
            def process_type(type_decl, outer_name=""):
                full_name = type_decl.name if not outer_name else f"{outer_name}.{type_decl.name}"
                public_methods_by_type.setdefault(full_name, [])

                from javalang.tree import (
                    ClassDeclaration,
                    InterfaceDeclaration,
                    EnumDeclaration,
                    MethodDeclaration,
                    ConstructorDeclaration,
                    FieldDeclaration,
                )

                # record the type itself
                if isinstance(type_decl, (ClassDeclaration, EnumDeclaration)):
                    classes.append(full_name)
                elif isinstance(type_decl, InterfaceDeclaration):
                    interfaces.append(full_name)

                # walk its members
                for _, node in type_decl.filter((MethodDeclaration, ConstructorDeclaration, FieldDeclaration)):
                    if isinstance(node, (MethodDeclaration, ConstructorDeclaration)):
                        mods = " ".join(sorted(node.modifiers)) if node.modifiers else ""
                        # build parameter list
                        params = []
                        for p in node.parameters:
                            t = p.type
                            tn = t.name if hasattr(t, "name") else str(t)
                            if getattr(t, "dimensions", None):
                                tn += "[]" * len(t.dimensions)
                            params.append(f"{tn} {p.name}")
                        param_str = ", ".join(params)

                        if hasattr(node, "return_type") and node.return_type:
                            rt = node.return_type
                            rtn = rt.name if hasattr(rt, "name") else str(rt)
                            signature = f"{mods} {rtn} {node.name}({param_str})".strip()
                        else:
                            signature = f"{mods} {node.name}({param_str})".strip()

                        methods.append(signature)
                        is_public = (
                            isinstance(type_decl, InterfaceDeclaration)
                            or "public" in getattr(node, "modifiers", [])
                        )
                        if is_public:
                            public_methods_by_type[full_name].append(signature)

                    elif isinstance(node, FieldDeclaration):
                        fm = " ".join(sorted(node.modifiers)) if node.modifiers else ""
                        ft = node.type.name if hasattr(node.type, "name") else str(node.type)
                        for decl in node.declarators:
                            var_sig = f"{fm} {ft} {decl.name}".strip()
                            global_vars.append(var_sig)

                # recurse into nested types
                for inner in getattr(type_decl, "body", []):
                    from javalang.tree import ClassDeclaration, InterfaceDeclaration, EnumDeclaration
                    if isinstance(inner, (ClassDeclaration, InterfaceDeclaration, EnumDeclaration)):
                        process_type(inner, outer_name=full_name)

            # start with the top‐level types
            for td in getattr(tree, "types", []):
                process_type(td)

            result[orig_file_path] = {
                "imports": imports_list,
                "interfaces": interfaces,
                "classes": classes,
                "methods": methods,
                "global_vars": global_vars,
                "public_methods": public_methods_by_type,
            }

        elif ext == ".py":
            # --- Python parsing using ast ---
            try:
                tree_py = ast.parse(code)
            except Exception as e:
                result[orig_file_path] = (
                    f"Error parsing Python file {mask_output(safe_file_path)}: "
                    f"{mask_output(str(e))}"
                )
                overall_success = False
                continue

            imports_list = []
            interfaces = []  # Python has no interfaces
            classes = []
            methods = []     # includes module-level & async functions
            global_vars = []
            public_methods_by_type = {}

            # helper to process a Python class (including nested)
            def process_py_class(node, outer_name=""):
                full_name = node.name if not outer_name else f"{outer_name}.{node.name}"
                classes.append(full_name)
                public_methods_by_type.setdefault(full_name, [])

                for stmt in node.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        params = [arg.arg for arg in stmt.args.args]
                        prefix = "async def" if isinstance(stmt, ast.AsyncFunctionDef) else "def"
                        sig = f"{prefix} {stmt.name}({', '.join(params)})"
                        methods.append(sig)
                        if not stmt.name.startswith("_"):
                            public_methods_by_type[full_name].append(sig)

                    elif isinstance(stmt, ast.ClassDef):
                        # nested class
                        process_py_class(stmt, outer_name=full_name)

                    elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                        # class-level variable
                        targets = []
                        if isinstance(stmt, ast.Assign):
                            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                        else:  # AnnAssign
                            if isinstance(stmt.target, ast.Name):
                                targets = [stmt.target.id]
                        for name in targets:
                            global_vars.append(f"{full_name}.{name}")

            # walk top‐level nodes
            for node in tree_py.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        as_part = f" as {alias.asname}" if alias.asname else ""
                        imports_list.append(f"import {alias.name}{as_part}")

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = ", ".join(
                        f"{alias.name}{' as ' + alias.asname if alias.asname else ''}"
                        for alias in node.names
                    )
                    imports_list.append(f"from {module} import {names}")

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    params = [arg.arg for arg in node.args.args]
                    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                    sig = f"{prefix} {node.name}({', '.join(params)})"
                    methods.append(sig)

                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            global_vars.append(target.id)

                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name):
                        global_vars.append(node.target.id)

                elif isinstance(node, ast.ClassDef):
                    process_py_class(node)

            result[orig_file_path] = {
                "imports": imports_list,
                "interfaces": interfaces,
                "classes": classes,
                "methods": methods,
                "global_vars": global_vars,
                "public_methods": public_methods_by_type,
            }

        else:
            result[orig_file_path] = f"Unsupported file type: {ext}"
            overall_success = False
            continue

    return {"success": overall_success, "output": result}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_get_code_structure",
            "description": (
                "Parses one or more Java or Python files to list all interfaces, "
                "classes, methods, global variables, and imports. Also provides "
                "a mapping of public methods within each type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "description": "List of paths to the Java or Python files to parse.",
                        "items": {"type": "string"},
                    }
                },
                "required": ["file_paths"],
                "additionalProperties": False,
                "strict": True,
            },
        },
        "internal": {
            "preservation_policy": "until-update",
            "type": "readonly",
        },
    }
