# src/drone_ai_pr_reviewer/scm_client.py
import logging
import requests # Using requests library for HTTP calls
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_config import PluginConfig
    from .models import ReviewComment, SCMPRDetails

logger = logging.getLogger(__name__)

# --- Constants for SCM API Interaction (Example for GitHub) ---
# These would be adjusted based on the target SCM
# For a multi-SCM client, these would be dynamically set or part of SCM-specific classes.
# GITHUB_API_BASE_URL = "https://api.github.com"

class BaseSCMClient:
    """
    Base class for SCM clients. Defines the interface.
    Actual implementations (e.g., GitHubClient, GitLabClient) would inherit this.
    For simplicity, we might start with a single client assuming one SCM (e.g. GitHub)
    and refactor later if multiple SCMs are supported.
    """
    def __init__(self, config: 'PluginConfig'):
        self.config = config
        self.headers = {
            "Accept": "application/vnd.github.v3+json", # Example, varies by SCM
            "Authorization": f"token {self.config.scm_token}",
            "X-GitHub-Api-Version": "2022-11-28" # Example for GitHub
        }
        # Determine API base URL
        # For GitHub.com: https://api.github.com
        # For self-hosted, this needs to be configurable, e.g. via PLUGIN_SCM_API_URL
        # self.api_base_url = config.scm_api_url or GITHUB_API_BASE_URL # Example
        
        # A more generic way, assuming GitHub for now if not specified
        self.api_base_url = getattr(config, 'scm_api_url', None) or "https://api.github.com"
        if "gitlab" in getattr(config, 'scm_provider', "github").lower(): # Example
            self.api_base_url = getattr(config, 'scm_api_url', None) or "https://gitlab.com/api/v4"
            self.headers["Accept"] = "application/json" # GitLab uses this
            self.headers["Authorization"] = f"Bearer {self.config.scm_token}"
            if "X-GitHub-Api-Version" in self.headers:
                del self.headers["X-GitHub-Api-Version"]
        # Add elif for bitbucket, azure_devops etc.

        logger.info(f"SCM Client initialized for base URL: {self.api_base_url}")


    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None, 
                 expected_status: int = 200, custom_headers: Optional[Dict] = None) -> Optional[Any]:
        """Helper method to make HTTP requests."""
        url = f"{self.api_base_url}{endpoint}"
        request_headers = self.headers.copy()
        if custom_headers:
            request_headers.update(custom_headers)
        
        try:
            logger.debug(f"Making SCM API {method} request to {url} with params {params} and data {json_data}")
            response = requests.request(method, url, headers=request_headers, params=params, json=json_data, timeout=30)
            
            if response.status_code == expected_status:
                if response.content: # Check if there is content to parse
                    # For 'diff' media type, content is text, not JSON
                    if custom_headers and custom_headers.get("Accept") == "application/vnd.github.v3.diff":
                        return response.text
                    return response.json()
                return True # For successful calls with no content (e.g., 204 No Content)
            else:
                logger.error(f"SCM API request to {url} failed with status {response.status_code}: {response.text[:500]}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"SCM API request to {url} encountered an exception: {e}", exc_info=True)
            return None

    def get_pr_details(self) -> Optional['SCMPRDetails']:
        """
        Fetches PR details like description, actual title (if not from CI env).
        This is needed because CI env vars might not have the full description.
        """
        if not (self.config.ci_repo_owner and self.config.ci_repo_name and self.config.ci_pr_number):
            logger.error("Cannot fetch PR details: Missing repo owner, name, or PR number in config.")
            return None
        
        # Example for GitHub:
        endpoint = f"/repos/{self.config.ci_repo_owner}/{self.config.ci_repo_name}/pulls/{self.config.ci_pr_number}"
        logger.info(f"Fetching PR details from SCM: {endpoint}")
        
        response_data = self._request("GET", endpoint)
        if response_data and isinstance(response_data, dict):
            # TODO: Map SCM-specific response to SCMPRDetails model
            # For GitHub:
            title = response_data.get("title", self.config.ci_pr_title or "N/A")
            description = response_data.get("body", "") # Body can be None
            if description is None: description = ""

            # Update config with fetched details if they were missing or to ensure canonical source
            self.config.ci_pr_title = title
            self.config.ci_pr_description = description
            logger.info(f"Successfully fetched PR details for PR #{self.config.ci_pr_number}.")
            
            # Return a more detailed object if needed, or just update config
            from .models import SCMPRDetails # Local import to avoid circular dependency at module level
            return SCMPRDetails(
                pr_id=self.config.ci_pr_number,
                title=title,
                description=description
                # Populate other fields if needed
            )
        logger.error(f"Failed to fetch or parse PR details for PR #{self.config.ci_pr_number}.")
        return None


    def get_pr_diff(self) -> Optional[str]:
        """
        Fetches the diff for the current pull request.
        The diffing strategy (full PR diff vs. compare commits) is determined
        by the calling logic in main.py based on the CI event.
        This method assumes it's getting the diff for the *entire* PR.
        """
        if not (self.config.ci_repo_owner and self.config.ci_repo_name and self.config.ci_pr_number):
            logger.error("Cannot fetch PR diff: Missing repo owner, name, or PR number.")
            return None

        # Example for GitHub:
        endpoint = f"/repos/{self.config.ci_repo_owner}/{self.config.ci_repo_name}/pulls/{self.config.ci_pr_number}"
        custom_headers = {"Accept": "application/vnd.github.v3.diff"} # SCM-specific media type for diff
        
        logger.info(f"Fetching full PR diff from SCM: {endpoint}")
        diff_text = self._request("GET", endpoint, custom_headers=custom_headers)
        
        if diff_text and isinstance(diff_text, str):
            logger.info(f"Successfully fetched PR diff (length: {len(diff_text)}).")
            return diff_text
        
        logger.error(f"Failed to fetch PR diff for PR #{self.config.ci_pr_number}.")
        return None

    def compare_commits_diff(self) -> Optional[str]:
        """
        Fetches the diff between two commits (base_sha and head_sha from config).
        Used for "synchronize" events.
        """
        if not (self.config.ci_repo_owner and self.config.ci_repo_name and self.config.ci_base_sha and self.config.ci_head_sha):
            logger.error("Cannot compare commits: Missing repo owner/name or base/head SHAs.")
            return None

        # Example for GitHub:
        endpoint = f"/repos/{self.config.ci_repo_owner}/{self.config.ci_repo_name}/compare/{self.config.ci_base_sha}...{self.config.ci_head_sha}"
        custom_headers = {"Accept": "application/vnd.github.v3.diff"}
        
        logger.info(f"Fetching commit comparison diff from SCM: {endpoint} ({self.config.ci_base_sha}..{self.config.ci_head_sha})")
        diff_text = self._request("GET", endpoint, custom_headers=custom_headers)

        if diff_text and isinstance(diff_text, str):
            logger.info(f"Successfully fetched commit comparison diff (length: {len(diff_text)}).")
            return diff_text
        
        logger.error(f"Failed to fetch commit comparison diff.")
        return None
        
    def get_target_branch_head_sha(self) -> Optional[str]:
        """
        Fetches the HEAD SHA of the PR's target branch.
        Needed for 'opened' PR events if DRONE_PULL_REQUEST_BASE_SHA is not available.
        """
        if not (self.config.ci_repo_owner and self.config.ci_repo_name and self.config.ci_target_branch):
            logger.error("Cannot fetch target branch head SHA: Missing repo owner/name or target branch.")
            return None

        # Example for GitHub: refs/heads/branch-name
        endpoint = f"/repos/{self.config.ci_repo_owner}/{self.config.ci_repo_name}/git/ref/heads/{self.config.ci_target_branch}"
        logger.info(f"Fetching target branch head SHA for '{self.config.ci_target_branch}' from: {endpoint}")
        
        response_data = self._request("GET", endpoint)
        if response_data and isinstance(response_data, dict) and "object" in response_data and "sha" in response_data["object"]:
            sha = response_data["object"]["sha"]
            logger.info(f"Successfully fetched target branch '{self.config.ci_target_branch}' head SHA: {sha}")
            return sha
        
        logger.error(f"Failed to fetch target branch head SHA for '{self.config.ci_target_branch}'. Response: {response_data}")
        return None


    def post_review_comments(self, comments: List['ReviewComment']) -> bool:
        """
        Posts review comments to the pull request.
        SCM APIs usually have a way to create a "review" with multiple comments.
        """
        if not comments:
            logger.info("No comments to post.")
            return True
        
        if not (self.config.ci_repo_owner and self.config.ci_repo_name and self.config.ci_pr_number and self.config.ci_head_sha):
            logger.error("Cannot post review comments: Missing repo owner, name, PR number, or head SHA.")
            return False

        # Example for GitHub: Create a Review with comments
        # https://docs.github.com/en/rest/pulls/reviews?apiVersion=2022-11-28#create-a-review-for-a-pull-request
        endpoint = f"/repos/{self.config.ci_repo_owner}/{self.config.ci_repo_name}/pulls/{self.config.ci_pr_number}/reviews"
        
        # GitHub's API expects comments in a specific format within the review payload
        # Each comment needs: path, body, line (for new code) or side & line (for old code/context)
        # For comments on added lines, it's often 'line' (line number in the diff relative to hunk)
        # or 'position' (number of lines from the start of the hunk). This needs careful mapping.
        # For simplicity, assuming 'line' refers to the line number in the new file that the LLM provided.
        # GitHub's API might require careful handling of line numbers (diff-relative vs file-absolute).
        # The `line` parameter for a new review comment is the line number in the *unified diff*.
        # This is NOT the absolute line number in the file.
        # We need to map our LLM's `lineNumber` (absolute in new file) to a diff-relative line number.
        # This is a complex part. For now, let's assume a simplification or placeholder.
        # TODO: Implement robust mapping from absolute file line number to diff-relative position for SCM API.
        #       This often involves re-parsing the diff or using detailed info from the diff parser.
        #       For now, we'll use the absolute line number, which might not always place comments correctly on all SCMs.

        review_comments_payload = []
        for comment in comments:
            # Find the correct line number mapping for this comment
            file_path = comment.file_path
            line_number = comment.line_number
            
            # Find the DiffFile that contains this file
            diff_file = next((f for f in self.config.diff_files if f.new_path == file_path), None)
            if not diff_file:
                logger.warning(f"Could not find diff file for path: {file_path}")
                continue
                
            # Find the correct hunk that contains this line
            correct_hunk = None
            for hunk_mapping in diff_file.hunk_line_mappings:
                if line_number in hunk_mapping:
                    correct_hunk = hunk_mapping
                    break
            
            if not correct_hunk:
                logger.warning(f"Could not find hunk containing line {line_number} in file {file_path}")
                continue
                
            # Get the diff-relative line number from the mapping
            _, diff_line_number = correct_hunk[line_number]
            
            review_comments_payload.append({
                "path": file_path,
                "body": comment.body,
                "line": diff_line_number, # Now using the correct diff-relative line number
                "side": "RIGHT" # For comments on added lines
            })

        payload = {
            "commit_id": self.config.ci_head_sha, # The SHA of the PR head to associate review with
            "event": "COMMENT", # Or "REQUEST_CHANGES", "APPROVE"
            "body": "AI Code Reviewer suggestions:", # Optional overall review body
            "comments": review_comments_payload
        }
        
        logger.info(f"Posting {len(comments)} review comments to PR #{self.config.ci_pr_number}.")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Review payload: {json.dumps(payload, indent=2)}")

        response_data = self._request("POST", endpoint, json_data=payload, expected_status=200) # GitHub returns 200 on success
        
        if response_data:
            logger.info("Successfully posted review comments.")
            return True
        
        logger.error("Failed to post review comments.")
        return False

# Example of how SCMClient might be chosen or instantiated
# def get_scm_client(config: 'PluginConfig') -> BaseSCMClient:
#     # provider = config.scm_provider
#     # if provider == "github":
#     #     return GitHubSCMClient(config)
#     # elif provider == "gitlab":
#     #     return GitLabSCMClient(config)
#     # else:
#     #     logger.error(f"Unsupported SCM provider: {provider}")
#     #     raise ValueError(f"Unsupported SCM provider: {provider}")
#     return BaseSCMClient(config) # For now, use the base which defaults to GitHub-like behavior