# admission/job_code_stats.py

from admission import admission_job
import os

@admission_job("code_stats")
def code_stats_job(repo_path, repo_info):
    """
    Admission job: Computes basic source code statistics.
    Adds 'source_file_count', 'total_loc', 'largest_file', 'largest_file_size'
    to repo_info['metadata'].  The 'largest_file' path is made relative
    to the repository root.
    """
    # Use the most up-to-date path (after clone, etc)
    local_path = repo_info.get("local_path", repo_path)

    # Define source file extensions you want to count
    ext_language = {
        ".java", ".py", ".js", ".ts", ".c", ".cpp", ".cs", ".go", ".rb", ".kt"
    }

    total_files  = 0
    total_loc    = 0
    largest_file = None
    largest_size = 0

    for root, _, files in os.walk(local_path):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ext_language:
                continue

            total_files += 1
            path = os.path.join(root, filename)
            try:
                # File size in bytes
                size = os.path.getsize(path)
                if size > largest_size:
                    largest_size = size
                    largest_file = path

                # Line count (LOC)
                with open(path, encoding="utf-8", errors="ignore") as f:
                    total_loc += sum(1 for _ in f)
            except Exception:
                # Skip unreadable files
                continue

    # Ensure metadata dict exists
    metadata = repo_info.setdefault("metadata", {})

    metadata["source_file_count"]  = total_files
    metadata["total_loc"]          = total_loc
    metadata["largest_file_size"]  = largest_size

    # Store the largest file path relative to the repo root, if any
    if largest_file:
        # os.path.relpath will normalize separators
        metadata["largest_file"] = os.path.relpath(largest_file, local_path)
    else:
        metadata["largest_file"] = None
