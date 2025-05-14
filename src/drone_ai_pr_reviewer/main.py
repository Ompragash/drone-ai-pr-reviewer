# src/drone_ai_pr_reviewer/main.py
import os
import sys
import asyncio # For running async LLM calls
import logging
import subprocess # For git commands
from urllib.parse import urlparse
from dotenv import load_dotenv # For local development using .env file

from .plugin_config import load_plugin_config, PluginConfig
from .llm_auth_helper import setup_liteLLM_provider_specific_env
from .llm_reviewer import LLMReviewer
from .scm_client import BaseSCMClient # Using BaseSCMClient for now
from .diff_parser import parse_diff_text
from .models import ReviewComment, DiffFile # Import DiffFile for type hinting
import minimatch # For exclude patterns

# Global logger for the module
logger = logging.getLogger("drone_ai_pr_reviewer") # Use a named logger

def setup_logging(log_level_str: str):
    """Configures basic logging for the plugin."""
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
        logger.warning(f"Invalid log level '{log_level_str}'. Defaulting to INFO.")
    
    # Basic configuration, can be made more sophisticated
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def validate_config(config: PluginConfig) -> bool:
    """Validate that all required configuration is present."""
    required_vars = [
        "llm_provider",
        "llm_model",
        "ci_repo_owner",
        "ci_repo_name",
        "ci_pr_number"
    ]
    
    missing = [var for var in required_vars if not getattr(config, var, None)]
    if missing:
        logger.error(f"Missing required configuration: {missing}")
        return False
    
    # Validate LLM provider
    if config.llm_provider not in ["openai", "azure", "ollama", "openrouter", "novita"]:
        logger.error(f"Invalid LLM provider: {config.llm_provider}")
        return False
    
    return True

def main_cli():
    """Main entry point for the plugin."""
    try:
        # Load config
        config = load_plugin_config()
        
        # Validate config
        if not validate_config(config):
            logger.error("Configuration validation failed. Exiting.")
            sys.exit(1)
            
        # Setup logging
        setup_logging(config.log_level or "INFO")
        
        # Setup LLM provider
        setup_liteLLM_provider_specific_env(config)
        
        # Create instances
        llm_reviewer = LLMReviewer(config)
        scm_client = BaseSCMClient(config)
        
        # Populate CI info
        populate_ci_environment_info(config, scm_client)
        
        # Run review
        success = asyncio.run(review_pr(config, scm_client, llm_reviewer))
        
        if not success:
            logger.error("PR review failed.")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main_cli()
    # Set LiteLLM's logger level as well if desired, or control its verbosity
    # For example, to reduce LiteLLM's own logging:
    # litellm_logger = logging.getLogger("LiteLLM")
    # litellm_logger.setLevel(logging.WARNING) # Or higher to make it less verbose

def get_git_remote_url(remote_name: str = "origin") -> Optional[str]:
    """Gets the URL of a given git remote using git command."""
    try:
        # Check if .git directory exists
        # This logic might need to be more robust depending on where the script is run from
        # DRONE_WORKSPACE is usually the root of the checkout
        repo_path = os.getenv("DRONE_WORKSPACE", os.getcwd())
        git_dir_path = os.path.join(repo_path, ".git")

        if not os.path.isdir(git_dir_path):
            logger.warning(f".git directory not found at {git_dir_path}. Cannot run git commands to get remote URL.")
            # Attempt to find .git in parent directories as a fallback for local testing
            current_dir = os.getcwd()
            found_git_root = None
            while current_dir != os.path.dirname(current_dir): # Stop at root
                if os.path.exists(os.path.join(current_dir, ".git")):
                    found_git_root = current_dir
                    break
                current_dir = os.path.dirname(current_dir)
            if not found_git_root:
                logger.warning("Could not find .git directory in current or parent paths.")
                return None
            repo_path = found_git_root # Execute git command from this found root

        cmd = ["git", "remote", "get-url", remote_name]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=repo_path)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.warning(f"Failed to get URL for remote '{remote_name}' (stderr: {result.stderr.strip()}). Trying 'git config'.")
            cmd_config = ["git", "config", "--get", f"remote.{remote_name}.url"]
            result_config = subprocess.run(cmd_config, capture_output=True, text=True, check=False, cwd=repo_path)
            if result_config.returncode == 0:
                return result_config.stdout.strip()
            logger.error(f"Failed to get URL for remote '{remote_name}' using 'git config' as well (stderr: {result_config.stderr.strip()}).")
            return None
    except FileNotFoundError:
        logger.error("'git' command not found. Ensure Git is installed and in PATH.")
        return None
    except Exception as e:
        logger.error(f"Exception while getting git remote URL: {e}", exc_info=True)
        return None

def populate_ci_environment_info(config: PluginConfig, scm_client: BaseSCMClient):
    """
    Populates the PluginConfig object with information derived from CI environment variables
    (e.g., Drone CI variables).
    """
    logger.info("Populating CI environment information into config...")
    config.ci_system = "drone" # Assuming Drone CI for now

    # --- Event Type ---
    config.ci_event_name = os.getenv("DRONE_BUILD_EVENT")
    pr_number_str = os.getenv("DRONE_PULL_REQUEST")

    if pr_number_str:
        try:
            config.ci_pr_number = int(pr_number_str)
            config.is_pr_event = True
        except ValueError:
            logger.error(f"Invalid DRONE_PULL_REQUEST value: {pr_number_str}. Not a number.")
            config.is_pr_event = False
    else:
        config.is_pr_event = False

    if not config.is_pr_event:
        logger.info("Not a PR event (DRONE_PULL_REQUEST not set or invalid). Skipping review process.")
        return

    # --- SHAs ---
    config.ci_head_sha = os.getenv("DRONE_COMMIT_SHA") or os.getenv("DRONE_COMMIT") or os.getenv("DRONE_COMMIT_AFTER")
    if not config.ci_head_sha:
        logger.error("Could not determine head SHA (DRONE_COMMIT_SHA / DRONE_COMMIT / DRONE_COMMIT_AFTER missing).")
        config.is_pr_event = False
        return
        
    # --- Determine Event Action and Base SHA ---
    if config.ci_event_name == "pull_request":
        config.is_pr_opened_event = True
        config.ci_event_action = "opened" # Or "reopened", etc. Drone might have more specific var.
        config.ci_base_sha = os.getenv("DRONE_PULL_REQUEST_BASE_SHA")
        if not config.ci_base_sha:
            logger.info("DRONE_PULL_REQUEST_BASE_SHA not found for 'opened' PR. Attempting to fetch target branch head.")
            # Target branch name is needed for this
            config.ci_target_branch = os.getenv("DRONE_TARGET_BRANCH")
            if config.ci_target_branch:
                fetched_base_sha = scm_client.get_target_branch_head_sha() # API call
                if fetched_base_sha:
                    config.ci_base_sha = fetched_base_sha
                else:
                    logger.error(f"Failed to fetch head SHA for target branch '{config.ci_target_branch}'. Cannot determine diff base.")
                    config.is_pr_event = False
                    return
            else:
                logger.error("DRONE_TARGET_BRANCH not set, cannot fetch base SHA for opened PR.")
                config.is_pr_event = False
                return

    elif config.ci_event_name == "push" and config.is_pr_event: # is_pr_event checks DRONE_PULL_REQUEST
        config.is_pr_synchronize_event = True
        config.ci_event_action = "synchronize"
        config.ci_base_sha = os.getenv("DRONE_COMMIT_BEFORE")
        if not config.ci_base_sha or config.ci_base_sha == "0000000000000000000000000000000000000000":
            logger.error(f"DRONE_COMMIT_BEFORE is missing or null for 'push' (synchronize) event on PR #{config.ci_pr_number}.")
            config.is_pr_event = False
            return
        if config.ci_base_sha == config.ci_head_sha:
            logger.info(f"Base SHA is same as Head SHA ({config.ci_head_sha}) for 'synchronize' event. No changes to review.")
            config.is_pr_event = False # Effectively no diff
            return
    else:
        logger.info(f"Unhandled DRONE_BUILD_EVENT '{config.ci_event_name}' for PR review logic, or not a clear PR update (e.g. push without DRONE_PULL_REQUEST).")
        config.is_pr_event = False
        return

    if not config.ci_base_sha:
        logger.error("Base SHA for diffing could not be determined.")
        config.is_pr_event = False
        return

    logger.info(f"Determined event action: {config.ci_event_action}, Base SHA: {config.ci_base_sha}, Head SHA: {config.ci_head_sha}")

    # --- Repository Info ---
    # Prioritize getting from local git, then DRONE_REPO_LINK
    local_git_url = get_git_remote_url("origin")
    config.ci_repo_link = local_git_url or os.getenv("DRONE_REPO_LINK")

    if config.ci_repo_link:
        try:
            # Simplified parsing logic - this needs to be robust as discussed
            parsed_url = urlparse(config.ci_repo_link)
            path_segments = [segment for segment in parsed_url.path.split('/') if segment]
            if path_segments and path_segments[-1].endswith(".git"):
                path_segments[-1] = path_segments[-1][:-4]
            
            # Basic heuristic: needs more SCM-specific logic here as per previous discussion
            if len(path_segments) >= 2:
                # This assumes last part is repo, everything before is owner/namespace
                config.ci_repo_name = path_segments[-1]
                config.ci_repo_owner = "/".join(path_segments[:-1])
                config.ci_repo_full_name = f"{config.ci_repo_owner}/{config.ci_repo_name}"
                logger.info(f"Parsed Repo: Owner='{config.ci_repo_owner}', Name='{config.ci_repo_name}' from link.")
            else:
                logger.error(f"Could not parse owner/repo from link: {config.ci_repo_link} (not enough path segments)")
        except Exception as e:
            logger.error(f"Error parsing repo link '{config.ci_repo_link}': {e}", exc_info=True)
    
    if not config.ci_repo_owner or not config.ci_repo_name:
         # Fallback to direct DRONE variables if parsing failed
        config.ci_repo_owner = config.ci_repo_owner or os.getenv("DRONE_REPO_OWNER")
        config.ci_repo_name = config.ci_repo_name or os.getenv("DRONE_REPO_NAME")
        if config.ci_repo_owner and config.ci_repo_name:
            config.ci_repo_full_name = f"{config.ci_repo_owner}/{config.ci_repo_name}"
            logger.info(f"Using direct DRONE_REPO_OWNER/NAME: Owner='{config.ci_repo_owner}', Name='{config.ci_repo_name}'.")
        else:
            logger.error("Could not determine repository owner and name. SCM operations will fail.")
            config.is_pr_event = False
            return

    # --- Other PR/Commit Info from CI ---
    config.ci_pr_title = os.getenv("DRONE_PULL_REQUEST_TITLE") # May be overridden by SCM API call
    config.ci_pr_link = os.getenv("DRONE_COMMIT_LINK") # Often the PR link for PR events
    config.ci_source_branch = os.getenv("DRONE_SOURCE_BRANCH")
    # config.ci_target_branch is already fetched if needed for base_sha
    config.ci_target_branch = config.ci_target_branch or os.getenv("DRONE_TARGET_BRANCH")


    config.ci_commit_message = os.getenv("DRONE_COMMIT_MESSAGE")
    config.ci_commit_author = os.getenv("DRONE_COMMIT_AUTHOR")
    config.ci_commit_author_email = os.getenv("DRONE_COMMIT_AUTHOR_EMAIL")

    logger.info("CI environment information population complete.")


async def review_pr(config: PluginConfig, scm_client: BaseSCMClient, llm_reviewer: LLMReviewer) -> bool:
    """
    Main Pull Request review process.
    """
    if not config.is_pr_event:
        logger.info("Not a valid PR event for review. Skipping.")
        return True # Not a failure, just nothing to do.

    # Fetch full PR details (especially description, and canonical title)
    logger.info(f"Fetching details for PR #{config.ci_pr_number}...")
    if not scm_client.get_pr_details(): # This updates config.ci_pr_description and config.ci_pr_title
        logger.error(f"Failed to fetch PR details for PR #{config.ci_pr_number}. Cannot proceed with full context.")
        # Decide if to proceed with potentially missing title/description or fail
        # For now, we'll proceed, LLMReviewer uses "N/A" if they are None.
    
    # Get diff text
    diff_text: Optional[str] = None
    if config.is_pr_opened_event:
        logger.info(f"Fetching full diff for opened PR #{config.ci_pr_number}...")
        diff_text = scm_client.get_pr_diff()
    elif config.is_pr_synchronize_event:
        logger.info(f"Fetching diff for synchronized PR #{config.ci_pr_number} (Base: {config.ci_base_sha}, Head: {config.ci_head_sha})...")
        diff_text = scm_client.compare_commits_diff()
    
    if not diff_text:
        logger.warning("No diff text could be retrieved. Skipping review.")
        return True # No diff means nothing to review, not a failure.

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Retrieved diff text (first 1000 chars):\n{diff_text[:1000]}")

    # Parse diff
    parsed_diff_files: List[DiffFile] = parse_diff_text(diff_text)
    if not parsed_diff_files:
        logger.info("No reviewable files found after parsing diff. Skipping review.")
        return True

    # Filter files based on exclude patterns
    final_files_to_review: List[DiffFile] = []
    if config.exclude_patterns:
        logger.info(f"Applying exclude patterns: {config.exclude_patterns}")
        for diff_file in parsed_diff_files:
            if diff_file.display_path and \
               not any(minimatch.match(diff_file.display_path, pattern) for pattern in config.exclude_patterns):
                final_files_to_review.append(diff_file)
            elif diff_file.display_path:
                logger.info(f"Excluding file due to pattern match: {diff_file.display_path}")
        if not final_files_to_review and parsed_diff_files:
            logger.info("All files excluded by patterns. Nothing to review.")
            return True
    else:
        final_files_to_review = parsed_diff_files
    
    logger.info(f"Found {len(final_files_to_review)} files to review after filtering.")

    all_review_comments: List[ReviewComment] = []
    review_tasks = []

    for diff_file in final_files_to_review:
        if not diff_file.display_path: # Should not happen if parsed correctly
            continue
        logger.info(f"Processing file for review: {diff_file.display_path}")
        for chunk_idx, chunk in enumerate(diff_file.chunks):
            logger.info(f"  Reviewing chunk {chunk_idx + 1}/{len(diff_file.chunks)} (header: {chunk.header.strip()})")
            # Create an async task for each chunk review
            task = llm_reviewer.get_review_for_chunk(
                file_path=diff_file.display_path,
                diff_chunk_content=chunk.content_for_llm
            )
            review_tasks.append((task, diff_file.display_path)) # Store path for context

    # Gather results from all chunk review tasks
    # This will run them concurrently
    llm_results_with_context = await asyncio.gather(*(task for task, _ in review_tasks), return_exceptions=True)

    for i, result_or_exc in enumerate(llm_results_with_context):
        original_file_path = review_tasks[i][1]
        if isinstance(result_or_exc, Exception):
            logger.error(f"Error reviewing chunk for file {original_file_path}: {result_or_exc}", exc_info=result_or_exc)
        elif isinstance(result_or_exc, list): # Expected list of dicts
            for review_item_dict in result_or_exc:
                # Convert dict to ReviewComment object
                # TODO: Implement robust mapping of LLM's lineNumber to SCM comment position
                # This is a placeholder, assuming LLM returns absolute line number in new file.
                # SCMs often need diff-relative line numbers or positions.
                try:
                    comment_line = int(str(review_item_dict.get("lineNumber")))
                    comment_body = str(review_item_dict.get("reviewComment", "")).strip()
                    if comment_body: # Only add if there's a comment
                        all_review_comments.append(
                            ReviewComment(
                                file_path=original_file_path,
                                line_number=comment_line,
                                body=comment_body
                            )
                        )
                except (ValueError, TypeError) as e:
                     logger.warning(f"Could not create ReviewComment from LLM output item {review_item_dict} for file {original_file_path}: {e}")
        else:
            logger.warning(f"Unexpected result type from LLM review for file {original_file_path}: {type(result_or_exc)}")


    if not all_review_comments:
        logger.info("No review comments generated by the LLM across all files/chunks.")
        return True

    logger.info(f"Total review comments to post: {len(all_review_comments)}")
    
    # Post comments to SCM
    success = scm_client.post_review_comments(all_review_comments)
    if success:
        logger.info("Successfully posted all review comments to SCM.")
    else:
        logger.error("Failed to post one or more review comments to SCM.")
        return False # Indicate failure
    
    return True


async def async_main():
    """
    Asynchronous main function to orchestrate the plugin.
    """
    config = load_plugin_config()
    setup_logging(config.log_level) # Configure logging early

    logger.info("Starting AI PR Reviewer Plugin...")
    logger.info(f"Plugin Version: {getattr(__import__('drone_ai_pr_reviewer'), '__version__', 'N/A')}") # Get version from __init__

    # Validate essential configurations
    if not config.llm_model:
        logger.critical("PLUGIN_LLM_MODEL is not configured. Cannot proceed.")
        return 1
    if not config.scm_token:
        logger.critical("PLUGIN_SCM_TOKEN is not configured. Cannot proceed.")
        return 1

    # Setup LLM auth helpers (sets provider-specific env vars if needed)
    setup_liteLLM_provider_specific_env(config)

    # Initialize SCM client
    # TODO: Implement SCM provider factory if supporting multiple SCMs
    # For now, BaseSCMClient is used, which has GitHub-like defaults.
    scm_client = BaseSCMClient(config)

    # Populate CI environment details into config (owner, repo, PR num, SHAs, etc.)
    # This might make SCM calls (e.g., to get target branch head)
    populate_ci_environment_info(config, scm_client)

    # Initialize LLM reviewer
    llm_reviewer = LLMReviewer(config)
    
    try:
        success = await review_pr(config, scm_client, llm_reviewer)
        logger.info(f"Plugin execution finished. Success: {success}")
        return 0 if success else 1
    except Exception as e:
        logger.critical(f"Unhandled exception in plugin execution: {e}", exc_info=True)
        return 1 # General failure

def main_cli():
    """
    CLI entry point. Loads .env for local dev.
    """
    # Load .env file if it exists (for local development)
    # In a real CI environment, variables are injected by the system.
    if os.path.exists(".env"):
        logger.info("Found .env file, loading environment variables for local development.")
        load_dotenv(override=True) # Override existing env vars if .env specifies them
    elif os.path.exists("../.env"): # Check one level up for monorepo structure
        logger.info("Found .env file in parent directory, loading for local development.")
        load_dotenv(dotenv_path="../.env", override=True)


    # Ensure PYTHONASYNCIODEBUG is set for more detailed asyncio debug logs if log level is DEBUG
    # if os.getenv("PLUGIN_LOG_LEVEL", "INFO").upper() == "DEBUG":
    #    os.environ["PYTHONASYNCIODEBUG"] = "1" # This can make asyncio very verbose

    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Plugin execution interrupted by user (KeyboardInterrupt).")
        return 130 # Standard exit code for Ctrl+C

if __name__ == "__main__":
    # This allows the script to be run directly for testing.
    # The Drone plugin will likely execute this main_cli function or call async_main.
    sys.exit(main_cli())