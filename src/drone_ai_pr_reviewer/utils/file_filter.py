from typing import List, Optional
from pathspec import PathSpec
from pathspec.patterns.gitwildmatch import GitWildMatchPattern

def filter_files_by_patterns(
    files: List[str],
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None
) -> List[str]:
    """
    Filter a list of files based on include and exclude patterns.
    
    Args:
        files: List of file paths to filter
        include_patterns: Optional list of patterns to include (git-style patterns)
        exclude_patterns: Optional list of patterns to exclude (git-style patterns)
        
    Returns:
        List of filtered file paths
    """
    if not files:
        return []
    
    # Create PathSpec objects for include/exclude patterns
    include_spec = None
    exclude_spec = None
    
    if include_patterns:
        include_spec = PathSpec.from_lines(GitWildMatchPattern, include_patterns)
    
    if exclude_patterns:
        exclude_spec = PathSpec.from_lines(GitWildMatchPattern, exclude_patterns)
    
    # First pass: Include files that match include patterns
    if include_spec:
        included_files = [f for f in files if include_spec.match_file(f)]
    else:
        included_files = files  # No include patterns means include everything
    
    # Second pass: Exclude files that match exclude patterns
    if exclude_spec:
        return [f for f in included_files if not exclude_spec.match_file(f)]
    
    return included_files

# Example usage:
if __name__ == "__main__":
    files = [
        "src/main.py",
        "src/utils/file_filter.py",
        "tests/test_main.py",
        "README.md",
        "requirements.txt"
    ]
    
    include_patterns = ["src/*.py"]
    exclude_patterns = ["src/utils/*"]
    
    filtered = filter_files_by_patterns(files, include_patterns, exclude_patterns)
    print(f"Filtered files: {filtered}")
