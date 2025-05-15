from unidiff import PatchSet, LINE_TYPE_ADDED, LINE_TYPE_REMOVED, LINE_TYPE_CONTEXT

# Test the API
patch_text = """diff --git a/file.txt b/file.txt
index 1234567..7654321 100644
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,4 @@
 line1
+new_line
 line2
 line3
"""

patch = PatchSet(patch_text)

for hunk in patch[0]:
    for line in hunk:
        print(f"Line type: {line.line_type}")
        print(f"Is context: {line.line_type == LINE_TYPE_CONTEXT}")
        print(f"Is added: {line.line_type == LINE_TYPE_ADDED}")
        print(f"Is removed: {line.line_type == LINE_TYPE_REMOVED}")
        print(f"Target line: {line.target_line_no}")
