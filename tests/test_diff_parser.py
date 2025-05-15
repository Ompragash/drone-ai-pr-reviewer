import unittest
import tempfile
import os
import subprocess
from src.drone_ai_pr_reviewer.diff_parser import parse_diff_text, get_git_diff
from src.drone_ai_pr_reviewer.models import DiffFile, DiffChunk


def setup_git_repo(temp_dir: str) -> None:
    """Set up a git repository with test configuration."""
    # Initialize git repo
    subprocess.run(['git', 'init'], cwd=temp_dir, check=True)
    
    # Configure git for test environment
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=temp_dir, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=temp_dir, check=True)
    subprocess.run(['git', 'config', 'commit.gpgsign', 'false'], cwd=temp_dir, check=True)


class TestDiffParser(unittest.TestCase):
    def test_parse_simple_diff(self):
        # Test with a known diff output
        diff_text = """\
diff --git a/src/file1.py b/src/file1.py
index 1234567..7654321 100644
--- a/src/file1.py
+++ b/src/file1.py
@@ -1,4 +1,5 @@
def main():
+    print("Hello")
     pass
 
 if __name__ == '__main__':
@@ -5,3 +5,4 @@ if __name__ == '__main__':
     main()
+    print("Goodbye")
 """
        result = parse_diff_text(diff_text)
        
        # Should have 1 file
        self.assertEqual(len(result), 1)
        
        # Verify file1
        file1 = result[0]
        self.assertEqual(file1.display_path, "src/file1.py")
        self.assertEqual(len(file1.chunks), 2)
        
        # First chunk should have added line
        chunk1 = file1.chunks[0]
        added_changes = [change for change in chunk1.changes if change["type"] == "add"]
        context_changes = [change for change in chunk1.changes if change["type"] == "context"]
        self.assertEqual(len(added_changes), 1, "Should have one added line")
        self.assertEqual(len(context_changes), 3, "Should have three context lines")
        self.assertEqual(added_changes[0]["content"].strip(), "print(\"Hello\")")
        
        # Second chunk should have added line
        chunk2 = file1.chunks[1]
        added_changes = [change for change in chunk2.changes if change["type"] == "add"]
        context_changes = [change for change in chunk2.changes if change["type"] == "context"]
        self.assertEqual(len(added_changes), 1, "Should have one added line")
        self.assertEqual(len(context_changes), 2, "Should have two context lines")
        self.assertEqual(added_changes[0]["content"].strip(), "print(\"Goodbye\")")

    def test_parse_diff_with_excludes(self):
        # Test with a known diff output
        diff_text = """\
diff --git a/src/file1.py b/src/file1.py
index 1234567..7654321 100644
--- a/src/file1.py
+++ b/src/file1.py
@@ -1,4 +1,5 @@
def main():
+    print("Hello")
     pass

diff --git a/tests/test_file.py b/tests/test_file.py
index 1234567..7654321 100644
--- a/tests/test_file.py
+++ b/tests/test_file.py
@@ -1,4 +1,5 @@
def test_main():
+    print("Hello")
     pass
"""
        # Test with exclude patterns
        result = parse_diff_text(diff_text, exclude_patterns=["**/tests/**"])
        self.assertEqual(len(result), 1)  # Only src/file1.py should be included
        self.assertEqual(result[0].display_path, "src/file1.py")

        # Test with include patterns
        result = parse_diff_text(diff_text, include_patterns=["src/*.py"])
        self.assertEqual(len(result), 1)  # Only src/file1.py should be included
        self.assertEqual(result[0].display_path, "src/file1.py")

        # Test with both include and exclude patterns
        result = parse_diff_text(diff_text, include_patterns=["*.py"], exclude_patterns=["**/tests/**"])
        self.assertEqual(len(result), 1)  # Only src/file1.py should be included
        self.assertEqual(result[0].new_path, "src/file1.py")


class TestGitDiffParser(unittest.TestCase):
    def test_parse_simple_diff(self):
        # Create a temporary git repository
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(['git', 'init'], cwd=temp_dir)
            
            # Create initial file
            file1_path = os.path.join(temp_dir, 'src', 'file1.py')
            os.makedirs(os.path.dirname(file1_path), exist_ok=True)
            with open(file1_path, 'w') as f:
                f.write("""
def main():
    pass

if __name__ == '__main__':
    main()
""")
            
            # Create second file
            file2_path = os.path.join(temp_dir, 'src', 'file2.py')
            with open(file2_path, 'w') as f:
                f.write("""
def main():
    pass

if __name__ == '__main__':
    main()
""")
            
            # Stage and commit initial files
            subprocess.run(['git', 'add', '.'], cwd=temp_dir)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=temp_dir)
            
            # Get initial commit hash
            base_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                    cwd=temp_dir, 
                                    capture_output=True, 
                                    text=True).stdout.strip()
            
            # Modify files
            with open(file1_path, 'w') as f:
                f.write("""
def main():
    print("Hello")
    pass

if __name__ == '__main__':
    main()
    print("Goodbye")
""")
            
            with open(file2_path, 'w') as f:
                f.write("""
def main():
    print("Hello")
    pass

if __name__ == '__main__':
    main()
    print("Goodbye")
""")
            
            # Stage and commit changes
            subprocess.run(['git', 'add', '.'], cwd=temp_dir, check=True)
            subprocess.run(['git', 'commit', '-m', 'Update files'], cwd=temp_dir, check=True)
            head_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                    cwd=temp_dir, 
                                    capture_output=True, 
                                    text=True, 
                                    check=True).stdout.strip()
            
            # Get diff
            diff_text = get_git_diff(base_sha, head_sha, cwd=temp_dir)
            result = parse_diff_text(diff_text)
            
            # Verify results
            self.assertEqual(len(result), 2)
            
            # Verify file1
            file1 = result[0]
            self.assertEqual(file1.new_path, "src/file1.py")
            self.assertEqual(len(file1.chunks), 2)
            
            # First chunk should have one added line
            added_changes = [change for change in file1.chunks[0].changes if change["type"] == "add"]
            self.assertEqual(len(added_changes), 1, "Should have one added line")
            self.assertEqual(added_changes[0]["content"].strip(), "print(\"Hello\")")
            
            # Second chunk should have one added line
            added_changes = [change for change in file1.chunks[1].changes if change["type"] == "add"]
            self.assertEqual(len(added_changes), 1, "Should have one added line")
            self.assertEqual(added_changes[0]["content"].strip(), "print(\"Goodbye\")")
            
            # Verify file2
            file2 = result[1]
            self.assertEqual(file2.new_path, "src/file2.py")
            self.assertEqual(len(file2.chunks), 2)
            
            # First chunk should have one added line
            added_changes = [change for change in file2.chunks[0].changes if change["type"] == "add"]
            self.assertEqual(len(added_changes), 1, "Should have one added line")
            self.assertEqual(added_changes[0]["content"].strip(), "print(\"Hello\")")
            
            # Second chunk should have one added line
            added_changes = [change for change in file2.chunks[1].changes if change["type"] == "add"]
            self.assertEqual(len(added_changes), 1, "Should have one added line")
            self.assertEqual(added_changes[0]["content"].strip(), "print(\"Goodbye\")")
        
        # Should have 2 files
        self.assertEqual(len(result), 2)
        
        # File 1 should have 2 hunks
        file1 = result[0]
        self.assertEqual(file1.new_path, "src/file1.py")
        self.assertEqual(file1.display_path, "src/file1.py")
        self.assertEqual(len(file1.chunks), 2)
        
        # First chunk of file1 should have added line
        hunk1 = file1.chunks[0]
        added_changes = [change for change in hunk1.changes if change["type"] == "add"]
        self.assertEqual(len(added_changes), 1)
        self.assertEqual(added_changes[0]["content"].strip(), "print(\"Hello\")")
        
        # Second chunk of file1 should have added line
        hunk2 = file1.chunks[1]
        added_changes = [change for change in hunk2.changes if change["type"] == "add"]
        self.assertEqual(len(added_changes), 1)
        self.assertEqual(added_changes[0]["content"].strip(), "print(\"Goodbye\")")
        
        # File 2 should be identical to file1
        file2 = result[1]
        self.assertEqual(file2.display_path, "src/file2.py")
        self.assertEqual(len(file2.chunks), 2)
        
        # Print debug info
        print("\nHunk 0 line mappings:", file1.hunk_line_mappings[0])
        print("Hunk 1 line mappings:", file1.hunk_line_mappings[1])
        
        # Verify line numbers mapping
        # First hunk should have one line number mapping
        self.assertEqual(len(file1.hunk_line_mappings[0]), 1)
        self.assertEqual(file1.hunk_line_mappings[0][1], (1, 1))
        
        # Second hunk should have one line number mapping
        self.assertEqual(len(file1.hunk_line_mappings[1]), 1)
        self.assertEqual(file1.hunk_line_mappings[1][1], (1, 1))

    def test_parse_diff_with_excludes(self):
        # Create a temporary git repository
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(['git', 'init'], cwd=temp_dir)
            
            # Create files
            file1_path = os.path.join(temp_dir, 'src', 'file1.py')
            os.makedirs(os.path.dirname(file1_path), exist_ok=True)
            with open(file1_path, 'w') as f:
                f.write("""
def main():
    pass

if __name__ == '__main__':
    main()
""")
            
            test_file_path = os.path.join(temp_dir, 'tests', 'test_file.py')
            os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
            with open(test_file_path, 'w') as f:
                f.write("""
def test_main():
    pass

if __name__ == '__main__':
    test_main()
""")
            
            # Stage and commit initial files
            subprocess.run(['git', 'add', '.'], cwd=temp_dir)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=temp_dir)
            
            # Get initial commit hash
            base_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                    cwd=temp_dir, 
                                    capture_output=True, 
                                    text=True).stdout.strip()
            
            # Modify files
            with open(file1_path, 'a') as f:
                f.write("""
    print("Hello")
    print("Goodbye")
""")
            
            with open(test_file_path, 'a') as f:
                f.write("""
    print("Hello")
    print("Goodbye")
""")
            
            # Stage and commit changes
            subprocess.run(['git', 'add', '.'], cwd=temp_dir)
            subprocess.run(['git', 'commit', '-m', 'Update files'], cwd=temp_dir)
            
            # Get diff
            diff_text = get_git_diff(base_sha, "HEAD", cwd=temp_dir)
            
            # Test with exclude patterns
            result = parse_diff_text(diff_text, exclude_patterns=["**/tests/**"])
            self.assertEqual(len(result), 1)  # Only src/file1.py should be included
            self.assertEqual(result[0].new_path, "src/file1.py")

            # Test with include patterns
            result = parse_diff_text(diff_text, include_patterns=["src/*.py"])
            self.assertEqual(len(result), 1)  # Only src/file1.py should be included
            self.assertEqual(result[0].new_path, "src/file1.py")

            # Test with both include and exclude patterns
            result = parse_diff_text(diff_text, include_patterns=["*.py"], exclude_patterns=["**/tests/**"])
            self.assertEqual(len(result), 1)  # Only src/file1.py should be included
            self.assertEqual(result[0].new_path, "src/file1.py")

class TestGitDiff(unittest.TestCase):
    def test_get_git_diff(self):
        # Test git diff functionality
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up git repository
            setup_git_repo(temp_dir)
            
            # Create initial file
            file1_path = os.path.join(temp_dir, 'src', 'file1.py')
            os.makedirs(os.path.dirname(file1_path), exist_ok=True)
            with open(file1_path, 'w') as f:
                f.write("""\
def main():
    pass

if __name__ == '__main__':
    main()
""")
            
            # Stage and commit initial file
            subprocess.run(['git', 'add', '.'], cwd=temp_dir, check=True)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=temp_dir, check=True)
            base_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                    cwd=temp_dir, 
                                    capture_output=True, 
                                    text=True, 
                                    check=True).stdout.strip()
            
            # Modify file
            with open(file1_path, 'a') as f:
                f.write("""
    print("Hello")
    print("Goodbye")
""")
            
            # Stage and commit changes
            subprocess.run(['git', 'add', '.'], cwd=temp_dir, check=True)
            subprocess.run(['git', 'commit', '-m', 'Update files'], cwd=temp_dir, check=True)
            head_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                    cwd=temp_dir, 
                                    capture_output=True, 
                                    text=True, 
                                    check=True).stdout.strip()
            
            # Get diff
            diff_text = get_git_diff(base_sha, head_sha, cwd=temp_dir)
            
            # Parse the diff
            files = parse_diff_text(diff_text)
            
            # Verify diff contains expected changes
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].new_path, "src/file1.py")
            self.assertTrue(any("print(\"Hello\")" in change["content"] for change in files[0].chunks[0].changes if change["type"] == "add"))
            self.assertTrue(any("print(\"Goodbye\")" in change["content"] for change in files[0].chunks[0].changes if change["type"] == "add"))


if __name__ == '__main__':
    unittest.main()
