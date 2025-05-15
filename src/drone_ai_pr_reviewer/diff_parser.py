# src/drone_ai_pr_reviewer/diff_parser.py
import logging
import subprocess
import re
from typing import List, Optional, Dict, Tuple
from .utils.file_filter import filter_files_by_patterns
from .models import DiffFile, DiffChunk

logger = logging.getLogger(__name__)

def get_git_diff(base_sha: str, head_sha: str, cwd: Optional[str] = None) -> str:
    """Get diff between two git commits.

    Args:
        base_sha: Base commit SHA
        head_sha: Head commit SHA
        cwd: Working directory for git command

    Returns:
        str: Git diff output

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    cmd = ["git", "diff", "-U0", base_sha, head_sha]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=cwd)
    return result.stdout

def parse_diff_text(
    diff_text: str,
    exclude_patterns: Optional[List[str]] = None,
    include_patterns: Optional[List[str]] = None
) -> List[DiffFile]:
    """
    Parses raw diff text (e.g., from git diff or SCM API) into a list of DiffFile objects.

    Args:
        diff_text: The raw diff output as a string.

    Returns:
        A list of DiffFile objects representing the parsed diff.
    """
    if not diff_text:
        return []

    if not diff_text or diff_text.isspace():
        logger.debug("Received empty diff text, returning no parsed files.")
        return []

    # Process the diff text
    result = []
    current_file = None
    current_chunk = None
    current_hunk_line = 0
    current_diff_line = 0
    
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            # Add the last file if it exists
            if current_file and current_chunk:
                current_file.chunks.append(current_chunk)
                current_file.hunk_line_mappings.append(current_chunk.hunk_line_mapping)
                result.append(current_file)
            
            paths = line.split()[2:4]  # Get the paths from "diff --git a/path b/path"
            display_path = paths[1].split("b/")[1] if len(paths) > 1 else None
            
            # Skip if file doesn't match patterns
            if not display_path or not filter_files_by_patterns([display_path], include_patterns, exclude_patterns):
                current_file = None
                current_chunk = None
                continue
                
            current_file = DiffFile(
                old_path=paths[0].split('a/')[1] if len(paths) > 0 else None,
                new_path=paths[1].split('b/')[1] if len(paths) > 1 else None,
                chunks=[],
                hunk_line_mappings=[]
            )
            current_chunk = None
            current_hunk_line = 0
            current_diff_line = 0
            
        elif line.startswith("@@") and current_file:
            # New hunk section
            if current_chunk:
                current_file.chunks.append(current_chunk)
                current_file.hunk_line_mappings.append(current_chunk.hunk_line_mapping)
            
            # Extract header from the hunk line
            header = line if line.startswith("@@") else ""
            current_chunk = DiffChunk(
                content=header + "\n",  # Start with header
                changes=[],
                header=header,
                hunk_line_mapping={}
            )
            current_hunk_line = 1
            current_diff_line = 1
            
        elif line.startswith("+") and current_chunk:
            # Added line
            current_chunk.content += line + "\n"
            current_chunk.changes.append({
                "type": "add",
                "content": line[1:],
                "ln": current_hunk_line,
                "ln2": None
            })
            current_chunk.hunk_line_mapping[current_hunk_line] = (current_hunk_line, current_diff_line)
            current_hunk_line += 1
            current_diff_line += 1
            
        elif line.startswith("-") and current_chunk:
            # Removed line
            current_chunk.content += line + "\n"
            current_chunk.changes.append({
                "type": "remove",
                "content": line[1:],
                "ln": None,
                "ln2": current_hunk_line
            })
            current_diff_line += 1
            
        elif line.startswith(" ") and current_chunk:
            # Context line
            current_chunk.content += line + "\n"
            current_chunk.changes.append({
                "type": "context",
                "content": line[1:],
                "ln": current_hunk_line,
                "ln2": current_hunk_line
            })
            current_chunk.hunk_line_mapping[current_hunk_line] = (current_hunk_line, current_diff_line)
            current_hunk_line += 1
            current_diff_line += 1
            
    # Add the last file if it exists
    if current_file and current_chunk:
        current_file.chunks.append(current_chunk)
        result.append(current_file)
    
    return result
    
    # Only process files that match the patterns
    filtered_files = [file for file in patch_set if file.path in filtered_paths]
    
    # Process each file
    result = []
    for patched_file in filtered_files:
        # Skip files that are only in the diff due to mode changes but no content change
        if not patched_file.is_removed_file and \
           not patched_file.is_added_file and \
           not patched_file.is_modified_file and \
           not patched_file.is_renamed_file: 
            logger.debug(f"Skipping file with no content changes (e.g. mode only): {patched_file.source_file} -> {patched_file.target_file}")
            continue
        
        # Skip deleted files as per common requirement (LLM can't comment on non-existent new lines)
        if patched_file.is_removed_file:
            logger.info(f"Skipping deleted file: {patched_file.source_file}")
            continue
        
        # For new files, source_file is often '/dev/null' or similar
        # For deleted files, target_file is often '/dev/null'
        new_path = patched_file.target_file
        if new_path.startswith("b/"): # unidiff often prefixes target files with 'b/'
            new_path = new_path[2:]
        
        old_path = patched_file.source_file
        if old_path.startswith("a/"): # unidiff often prefixes source files with 'a/'
            old_path = old_path[2:]
        
        # Check for /dev/null to correctly set paths for new/deleted (though we skip deleted)
        if new_path == "/dev/null": # Should have been caught by is_removed_file
             logger.warning(f"File considered not deleted but target is /dev/null: {old_path}")
             continue 
        if old_path == "/dev/null": # This indicates a new file
            is_new = True
            old_p = None
        else:
            is_new = patched_file.is_added_file # More direct check
            old_p = old_path

        diff_file_model = DiffFile(
            old_path=old_p,
            new_path=new_path,
            is_new_file=is_new,
            is_deleted_file=patched_file.is_removed_file,
            is_renamed_file= (old_p is not None and new_path is not None and old_p != new_path and not is_new and not patched_file.is_removed_file), # Heuristic for rename
            diff_file_native_obj=patched_file # Store the original unidiff object
        )

        for hunk in patched_file:
            # Construct the diff content for the LLM for this hunk
            # This should include context lines, added lines, removed lines,
            # and potentially line numbers from the diff hunk itself.
            # The prompt example used:
            # ```diff
            # ${chunk.content}  <-- This is usually the hunk header line like @@ -1,5 +1,7 @@
            # ${chunk.changes.map((c) => `${c.ln ? c.ln : c.ln2} ${c.content}`).join("\n")} <-- Lines with their diff line numbers
            # ```
            # We need to replicate this formatting.
            
            # Track line numbers for mapping
            current_chunk.hunk_line_mapping = {}
            target_line = 1  # Line number in the target file
            source_line = 1  # Line number in the source file
            diff_line = 1  # Line number in the diff

            # Add line numbers for each line in the chunk
            for change in current_chunk.changes:
                if change["type"] in ["add", "context"]:
                    current_chunk.hunk_line_mapping[target_line] = (target_line, diff_line)
                    target_line += 1
                elif change["type"] == "remove":
                    source_line += 1
                diff_line += 1

            # Store the line mapping for this hunk
            diff_file_model.hunk_line_mappings.append(current_chunk.hunk_line_mapping)

            chunk_content = str(hunk)
            chunk_changes = [
                {
                    "ln": line.target_line_no if line.target_line_no else None,
                    "ln2": line.source_line_no if line.source_line_no else None,
                    "content": line.value
                }
                for line in hunk
            ]

            header = "" # Default empty header
            header_match = re.search(r'@@ .+ @@', chunk_content)
            if header_match:
                header = header_match.group(0)

            diff_file_model.chunks.append(DiffChunk(
                content=chunk_content,
                changes=chunk_changes,
                header=header,
                hunk_line_mapping=current_chunk.hunk_line_mapping
            ))

        if diff_file_model.chunks: # Only add file if it has reviewable chunks
            parsed_files.append(diff_file_model)
        else:
            logger.info(f"Skipping file {new_path} as it has no reviewable chunks after parsing.")

    logger.info(f"Parsed {len(parsed_files)} files from diff text.")
    return parsed_files

# Example usage (for testing this module standalone):
# if __name__ == '__main__':
#     sample_diff = """
# diff --git a/file1.txt b/file1.txt
# index 0123456..789abcd 100644
# --- a/file1.txt
# +++ b/file1.txt
# @@ -1,3 +1,4 @@
#  line one
# -line two
# +line two modified
#  line three
# +line four
# diff --git a/new_file.txt b/new_file.txt
# new file mode 100644
# index 0000000..abcdefg
# --- /dev/null
# +++ b/new_file.txt
# @@ -0,0 +1 @@
# +This is a new file.
# """
#     logging.basicConfig(level=logging.DEBUG)
#     parsed = parse_diff_text(sample_diff)
#     for p_file in parsed:
#         logger.debug(f"File: {p_file.display_path}, New: {p_file.is_new_file}, Chunks: {len(p_file.chunks)}")
#         for chunk_idx, p_chunk in enumerate(p_file.chunks):
#             logger.debug(f"  Chunk {chunk_idx+1} Header: {p_chunk.header}")
#             logger.debug(f"  Chunk Content for LLM:\n{p_chunk.content_for_llm}")