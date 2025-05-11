# modules/tools_utils.py

"""
This module provides functions shared between multiple tools.
"""

__all__ = [
    'group_paths',
]

import os

def group_paths(paths):
    """
    Groups a flat list of file paths into a nested structure by compressing common non-diverging path segments.
    
    Each file path is split by the OS separator (os.sep) and directories with only one child are merged.
    For example, given:
        ["dir/file1.txt", "dir/subdir/file2.txt", "file3.txt"]
    it returns a nested list structure that minimizes repeating path segments.
    
    Returns:
        list: A nested list structure for the file paths.
    """
    tree = {}
    for path in paths:
        parts = path.split(os.sep)
        node = tree
        for part in parts:
            if part not in node:
                node[part] = {}
            node = node[part]
    
    def compress_node(node):
        result = []
        for key in sorted(node.keys()):
            full_key = key
            child = node[key]
            while child and len(child) == 1:
                next_key = next(iter(child))
                full_key = full_key + os.sep + next_key
                child = child[next_key]
            children = compress_node(child) if child else []
            if children:
                result.append([full_key, children])
            else:
                result.append(full_key)
        return result
    
    return compress_node(tree)
