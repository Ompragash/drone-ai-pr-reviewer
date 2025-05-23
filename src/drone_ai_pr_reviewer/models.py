# src/drone_ai_pr_reviewer/models.py
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple

@dataclass
class ReviewComment:
    """
    Represents a single review comment to be posted to the SCM.
    """
    file_path: str
    line_number: int # Line number in the file (relative to the diff hunk or absolute in new file)
    body: str

@dataclass
class DiffChunk:
    """
    Represents a chunk of changes within a diff file.
    """
    content: str # The formatted diff content for this chunk to send to LLM
    changes: List[Dict[str, Any]] # List of line changes with line numbers and content
    header: str # The hunk header line (e.g., @@ -1,7 +1,7 @@)
    hunk_line_mapping: Dict[int, Tuple[int, int]] = field(default_factory=dict) # Maps target line numbers to (hunk_line_number, diff_line_number)

    @property
    def content_for_llm(self) -> str:
        """Format the chunk content for LLM review."""
        lines = []
        if self.header:
            lines.append(self.header)
        
        for change in self.changes:
            line_num = change.get('ln') or change.get('ln2') or ''
            content = change.get('content', '')
            lines.append(f"{line_num} {content}")
        
        return '\n'.join(lines)

@dataclass
class DiffFile:
    """
    Represents a single file in a diff.
    """
    old_path: Optional[str] # Path before changes (None for new files)
    new_path: Optional[str] # Path after changes (None for deleted files, though we filter those)
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_renamed_file: bool = False
    chunks: List[DiffChunk] = field(default_factory=list)
    hunk_line_mappings: List[Dict[int, Tuple[int, int]]] = field(default_factory=list)  # Maps target line numbers to (hunk_line_number, diff_line_number)
    diff_file_native_obj: Optional[Any] = None # Store the original object from the diff parsing library for richer access if needed

    @property
    def display_path(self) -> Optional[str]:
        """Returns the path to display or use for SCM comments (usually new_path)."""
        return self.new_path if self.new_path != "/dev/null" else self.old_path


# Placeholder for PR details fetched from SCM API, if not fully covered by CI env vars
@dataclass
class SCMPRDetails:
    pr_id: int # Or str depending on SCM
    title: str
    description: str
    # Add more fields as needed: author, created_at, base_sha, head_sha etc.
    # These would supplement what's in PluginConfig.ci_... if needed.