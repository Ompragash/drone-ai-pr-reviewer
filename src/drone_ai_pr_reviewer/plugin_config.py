# src/drone_ai_pr_reviewer/plugin_config.py
import os
from dataclasses import dataclass, field
from typing import Optional, List

# Default values for optional parameters
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 700
DEFAULT_TOP_P = 1.0
DEFAULT_EXCLUDE_PATTERNS = ""
DEFAULT_LOG_LEVEL = "INFO"

@dataclass
class PluginConfig:
    """
    Holds all configuration for the AI PR Reviewer plugin,
    primarily sourced from PLUGIN_ prefixed environment variables.
    """

    # --- Core LLM Settings ---
    llm_model: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_LLM_MODEL")
    )
    llm_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_LLM_API_KEY")
    ) # Handled as a secret by CI
    llm_api_base: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_LLM_API_BASE")
    )

    # --- Optional LLM Parameters ---
    temperature: float = field(
        default_factory=lambda: float(os.getenv("PLUGIN_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("PLUGIN_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
    )
    top_p: float = field(
        default_factory=lambda: float(os.getenv("PLUGIN_TOP_P", str(DEFAULT_TOP_P)))
    )
    # Consider adding:
    # frequency_penalty: Optional[float] = field(default_factory=lambda: float(os.getenv("PLUGIN_FREQUENCY_PENALTY", "0.0")) if os.getenv("PLUGIN_FREQUENCY_PENALTY") else None)
    # presence_penalty: Optional[float] = field(default_factory=lambda: float(os.getenv("PLUGIN_PRESENCE_PENALTY", "0.0")) if os.getenv("PLUGIN_PRESENCE_PENALTY") else None)


    # --- Optional Provider-Specific Configuration ---
    azure_api_version: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_AZURE_API_VERSION")
    )
    vertex_project: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_VERTEXAI_PROJECT")
    )
    vertex_location: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_VERTEXAI_LOCATION")
    )
    aws_region_name: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_AWS_REGION_NAME")
    )

    # --- SCM Settings ---
    scm_token: Optional[str] = field(
        default_factory=lambda: os.getenv("PLUGIN_SCM_TOKEN")
    ) # Handled as a secret by CI
    # Future:
    # scm_provider: str = field(default_factory=lambda: os.getenv("PLUGIN_SCM_PROVIDER", "github").lower()) # e.g. github, gitlab, bitbucket_server, azure_devops
    # scm_api_url: Optional[str] = field(default_factory=lambda: os.getenv("PLUGIN_SCM_API_URL")) # For self-hosted SCMs


    # --- Plugin Behavior ---
    exclude_patterns: List[str] = field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("PLUGIN_EXCLUDE_PATTERNS", DEFAULT_EXCLUDE_PATTERNS).split(',') if p.strip()
        ]
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("PLUGIN_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    )

    # --- CI Environment Information (to be populated by main.py from CI system variables) ---
    ci_system: Optional[str] = None
    ci_event_name: Optional[str] = None
    ci_event_action: Optional[str] = None

    ci_repo_owner: Optional[str] = None
    ci_repo_name: Optional[str] = None
    ci_repo_full_name: Optional[str] = None
    ci_repo_link: Optional[str] = None
    
    ci_pr_number: Optional[int] = None
    ci_pr_title: Optional[str] = None
    ci_pr_description: Optional[str] = None # This will be fetched via SCM API
    ci_pr_link: Optional[str] = None

    ci_source_branch: Optional[str] = None
    ci_target_branch: Optional[str] = None

    ci_head_sha: Optional[str] = None
    ci_base_sha: Optional[str] = None
    
    ci_commit_message: Optional[str] = None
    ci_commit_author: Optional[str] = None
    ci_commit_author_email: Optional[str] = None

    is_pr_event: bool = False
    is_pr_opened_event: bool = False
    is_pr_synchronize_event: bool = False


    def __post_init__(self):
        if not self.llm_model:
            print("WARN: [PluginConfig] PLUGIN_LLM_MODEL is not set.")
        
        if not self.scm_token:
            print("WARN: [PluginConfig] PLUGIN_SCM_TOKEN is not set.")

        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_log_levels:
            print(f"WARN: [PluginConfig] Invalid PLUGIN_LOG_LEVEL '{self.log_level}'. Defaulting to '{DEFAULT_LOG_LEVEL}'.")
            self.log_level = DEFAULT_LOG_LEVEL

def load_plugin_config() -> PluginConfig:
    """
    Factory function to create and return a PluginConfig instance.
    """
    # TODO: Initialize logging here based on config.log_level
    # import logging
    # logging.basicConfig(level=getattr(logging, PluginConfig().log_level, logging.INFO),
    #                     format='%(asctime)s - %(levelname)s - %(message)s')
    # logger = logging.getLogger(__name__) # or a global logger
    # logger.info("Plugin configuration loaded.")
    return PluginConfig()# src/drone_ai_pr_reviewer/llm_auth_helper.py
import os
import logging # Using standard logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_config import PluginConfig

logger = logging.getLogger(__name__)

def setup_liteLLM_provider_specific_env(config: 'PluginConfig'):
    """
    Sets up provider-specific environment variables that LiteLLM might expect,
    based on the plugin configuration.
    This is primarily for settings like project IDs or regions, as API key,
    base URL, and API version are intended to be passed directly to
    the litellm.completion() call.

    Args:
        config: The PluginConfig instance.
    """
    if not config.llm_model:
        logger.info("No LLM model specified in config, skipping provider-specific env setup for LiteLLM.")
        return

    logger.info(f"Setting up provider-specific environment for LiteLLM based on model: {config.llm_model}")

    provider_part = ""
    # A simple way to infer provider from model string like "provider/model_name"
    if "/" in config.llm_model:
        provider_part = config.llm_model.split('/')[0].lower()
    
    # --- Vertex AI ---
    # LiteLLM uses VERTEXAI_PROJECT and VERTEXAI_LOCATION environment variables.
    if provider_part == "vertex_ai" or \
       (provider_part == "google" and (config.vertex_project or config.vertex_location)) or \
       ("vertex_ai" in config.llm_model.lower()): # Broader check
        
        if config.vertex_project:
            os.environ["VERTEXAI_PROJECT"] = config.vertex_project
            logger.info(f"Set environment variable VERTEXAI_PROJECT to '{config.vertex_project}'")
        else:
            # This might be okay if gcloud ADC is fully configured with a default project.
            logger.info("PLUGIN_VERTEXAI_PROJECT not set. Relying on gcloud ADC or other defaults for Vertex AI project.")

        if config.vertex_location:
            os.environ["VERTEXAI_LOCATION"] = config.vertex_location
            logger.info(f"Set environment variable VERTEXAI_LOCATION to '{config.vertex_location}'")
        else:
            # This might be okay if gcloud ADC is fully configured with a default location.
            logger.info("PLUGIN_VERTEXAI_LOCATION not set. Relying on gcloud ADC or other defaults for Vertex AI location.")
    
    # --- AWS Bedrock ---
    # LiteLLM typically uses standard AWS SDK env vars (AWS_ACCESS_KEY_ID, etc., AWS_DEFAULT_REGION)
    # or IAM roles. PLUGIN_AWS_REGION_NAME allows explicit override/setting of region.
    if provider_part == "bedrock" or \
       (config.aws_region_name and ("bedrock" in config.llm_model.lower() or provider_part == "aws")): # Heuristic
        
        if config.aws_region_name:
            os.environ["AWS_REGION_NAME"] = config.aws_region_name # LiteLLM uses this for Bedrock
            os.environ["AWS_DEFAULT_REGION"] = config.aws_region_name # Also good practice for AWS SDK
            logger.info(f"Set AWS_REGION_NAME/AWS_DEFAULT_REGION to '{config.aws_region_name}' for Bedrock.")
        else:
            # This is okay if the execution environment (e.g., EC2 instance role, Lambda role)
            # or standard AWS env vars already define the region.
            logger.info("PLUGIN_AWS_REGION_NAME not set or empty. "
                        "Relying on default AWS SDK configuration for Bedrock region.")

    # --- Azure OpenAI ---
    # AZURE_API_VERSION, AZURE_API_KEY (from PLUGIN_LLM_API_KEY), and AZURE_API_BASE (from PLUGIN_LLM_API_BASE)
    # are primarily handled by passing them as direct keyword arguments to litellm.completion().
    # This section is a placeholder if other Azure-specific ENV VARS were ever needed by LiteLLM.
    if provider_part == "azure":
         logger.info("For Azure OpenAI, API Key, Base URL, and API Version are typically passed "
                     "directly to LiteLLM calls rather than set as environment variables by this helper. "
                     "Ensure PLUGIN_AZURE_API_VERSION is set if using Azure.")
         if not config.azure_api_version:
             logger.warning("Azure model indicated or 'azure' in model name, but PLUGIN_AZURE_API_VERSION is not set. "
                            "This is often required for Azure OpenAI calls.")

    # Add more provider-specific environment variable setups here if they arise
    # and are not better handled by direct kwargs to litellm.completion().

    logger.info("LiteLLM provider-specific environment setup check complete.")