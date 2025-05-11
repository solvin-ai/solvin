#!/usr/bin/env python3
"""
This script reads an input file containing multiple sections – each section starts with a header block in the format:

─────────────────────────────────────────────
File: <file_path>
─────────────────────────────────────────────
<file content>
─────────────────────────────────────────────

The script parses the input and writes each file to the indicated path (creating directories as needed).
"""

import re
import sys
import os

def split_into_files(input_text):
    """
    Splits the input text into a list of (file_path, content) tuples.

    The regex used here expects a header block consisting of:
      • A line of dashes (either Unicode “─” or ASCII “-”).
      • A line starting with "File:" followed by the file name.
      • A line of dashes (at least 10 consecutive dashes, Unicode or ASCII) acting as a separator.
      • Then the file content until the next header block or the end of the file.
    """
    pattern = re.compile(
        r"^(?:[─-]+\s*\n)File:\s*(.*?)\s*\n(?:[─-]{10,}\s*\n)(.*?)(?=^(?:[─-]+\s*\n)File:|\Z)",
        re.MULTILINE | re.DOTALL
    )
    
    files = []
    for match in pattern.finditer(input_text):
        file_path = match.group(1).strip()
        content = match.group(2).rstrip()  # Remove trailing whitespace/newlines
        files.append((file_path, content))
    return files

def write_file(file_path, content):
    """
    Writes the given content to file_path, creating any intermediate directories as needed.
    """
    # Ensure the target directory exists.
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote file: {file_path}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 split_files.py <input_file>")
        sys.exit(1)
    
    input_filename = sys.argv[1]
    if not os.path.isfile(input_filename):
        print(f"Error: File {input_filename} does not exist.")
        sys.exit(1)
    
    with open(input_filename, "r", encoding="utf-8") as infile:
        input_text = infile.read()
    
    file_entries = split_into_files(input_text)
    if not file_entries:
        print("No file sections found. Please check the input file format.")
        sys.exit(1)
    
    for file_path, content in file_entries:
        write_file(file_path, content)
    
    print("All files have been generated successfully.")

if __name__ == "__main__":
    main()
