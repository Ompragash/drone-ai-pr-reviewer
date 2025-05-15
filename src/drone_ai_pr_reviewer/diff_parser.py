# src/drone_ai_pr_reviewer/diff_parser.py
import logging
from typing import List, Optional, Dict, Tuple
from unidiff import PatchSet
from unidiff.patch import LineType

from .models import DiffFile, DiffChunk

logger = logging.getLogger(__name__)

def parse_diff_text(diff_text: str) -> List[DiffFile]:
    """
    Parses raw diff text (e.g., from git diff or SCM API) into a list of DiffFile objects.

    Args:
        diff_text: The raw diff output as a string.

    Returns:
        A list of DiffFile objects representing the parsed diff.
    """
    if not diff_text:
        logger.info("Received empty diff text, returning no parsed files.")
        return []

    parsed_files: List[DiffFile] = []
    try:
        # unidiff expects bytes or a file-like object, ensure diff_text is string
        # If diff_text is already a string, PatchSet(diff_text) should work.
        # If it needs to be file-like, io.StringIO can be used.
        patch_set = PatchSet(diff_text)
    except Exception as e:
        logger.error(f"Failed to parse diff text with unidiff: {e}", exc_info=True)
        # Log a snippet of the diff text for debugging, be careful with sensitive info
        logger.debug(f"Problematic diff text (first 500 chars): {diff_text[:500]}")
        return []

    for patched_file in patch_set:
        # Skip files that are only in the diff due to mode changes but no content change
        if not patched_file.is_removed_file and \
           not patched_file.is_added_file and \
           not patched_file.is_modified_file and \
           not patched_file.is_renamed_file: # Check if unidiff has is_renamed_file or similar
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
            hunk_line_mapping: Dict[int, Tuple[int, int]] = {}  # Maps target line number to (hunk_line_number, diff_line_number)
            current_hunk_line = 1  # Line number within the hunk
            current_diff_line = 1  # Line number in the diff (for SCM API)

            for line in hunk:
                if line.target_line is not None:  # Only track lines in the new file
                    hunk_line_mapping[line.target_line] = (current_hunk_line, current_diff_line)
                    
                # Increment line numbers based on line type
                if line.is_context:
                    current_hunk_line += 1
                    current_diff_line += 1
                elif line.is_added:
                    current_hunk_line += 1
                    current_diff_line += 1
                elif line.is_removed:
                    current_diff_line += 1

            # Store the line mapping for this hunk
            diff_file_model.hunk_line_mappings.append(hunk_line_mapping)

            # Add the hunk to the DiffFile
            diff_file_model.chunks.append(DiffChunk(
                content=str(hunk),
                changes=[
                    {
                        "ln": line.target_line_no if line.target_line_no else None,
                        "ln2": line.source_line_no if line.source_line_no else None,
                        "content": line.value
                    }
                    for line in hunk
                ],
                hunk_line_mapping=hunk_line_mapping  # Store mapping for this hunk
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