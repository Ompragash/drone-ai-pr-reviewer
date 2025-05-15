# src/drone_ai_pr_reviewer/llm_reviewer.py
import json
import logging
import litellm  # type: ignore
from string import Template
import importlib.resources # For loading prompt from package data
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_config import PluginConfig
    from .models import ReviewComment # Assuming a ReviewComment data model

logger = logging.getLogger(__name__)

class LLMReviewer:
    def __init__(self, config: 'PluginConfig'):
        """
        Initializes the LLMReviewer.

        Args:
            config: The plugin configuration object.
        """
        self.config = config
        self.prompt_template: Optional[Template] = None
        self._load_prompt_template()

    def _load_prompt_template(self):
        """Loads the review prompt template from the packaged file."""
        try:
            # For Python 3.9+
            prompt_file_ref = importlib.resources.files('drone_ai_pr_reviewer.prompts').joinpath('default_review_prompt.txt')
            prompt_template_str = prompt_file_ref.read_text(encoding='utf-8')
        except AttributeError: # Fallback for Python < 3.9
            try:
                with importlib.resources.path('drone_ai_pr_reviewer.prompts', 'default_review_prompt.txt') as p_path:
                    with open(p_path, 'r', encoding='utf-8') as f:
                        prompt_template_str = f.read()
            except FileNotFoundError:
                logger.error("Prompt template file 'default_review_prompt.txt' not found in package.")
                prompt_template_str = "Review this diff for file ${file_to}:\n${diff_chunk_content}" # Basic fallback
        except FileNotFoundError: # Catch if .files() itself fails to find the package path
            logger.error("Prompt template file 'default_review_prompt.txt' not found (package path issue).")
            prompt_template_str = "Review this diff for file ${file_to}:\n${diff_chunk_content}" # Basic fallback
        
        self.prompt_template = Template(prompt_template_str)
        logger.info("Prompt template loaded.")


    def _create_prompt_messages(self, file_path: str, diff_chunk_content: str) -> List[Dict[str, str]]:
        """
        Creates the list of messages for the LLM API call using the prompt template.
        """
        if not self.prompt_template:
            logger.error("Prompt template not loaded. Cannot create prompt messages.")
            # Return a minimal prompt or raise an error
            return [{"role": "user", "content": f"Review this code diff for {file_path}:\n{diff_chunk_content}"}]

        pr_title = self.config.ci_pr_title or "N/A" # Fetched via SCM API or from CI env
        pr_description = self.config.ci_pr_description or "N/A" # Fetched via SCM API

        try:
            formatted_prompt_content = self.prompt_template.substitute(
                file_to=file_path,
                pr_title=pr_title,
                pr_description=pr_description,
                diff_chunk_content=diff_chunk_content
            )
        except KeyError as e:
            logger.error(f"Missing placeholder in prompt template: {e}. Using raw diff content.")
            # Fallback if template substitution fails
            formatted_prompt_content = f"Review this code diff for {file_path} (PR: {pr_title}):\n{diff_chunk_content}"

        # Create messages array with both system and user messages
        messages = [
            {"role": "system", "content": formatted_prompt_content},
            {"role": "user", "content": "Please review the code changes above and provide specific, actionable feedback in JSON format."}
        ]
        return messages

    async def get_review_for_chunk(self, file_path: str, diff_chunk_content: str) -> List[Dict[str, Any]]:
        """
        Gets AI review comments for a specific diff chunk.

        Args:
            file_path: The path of the file being reviewed.
            diff_chunk_content: The diff content of the chunk.

        Returns:
            A list of review data dictionaries parsed from the LLM response.
            Each dictionary should have "lineNumber" and "reviewComment".
            Returns an empty list if no valid comments are found or an error occurs.
        """
        if not self.config.llm_model:
            logger.error("LLM model is not configured. Cannot get review.")
            return []

        messages = self._create_prompt_messages(file_path, diff_chunk_content)

        kwargs_for_litellm: Dict[str, Any] = {
            "model": self.config.llm_model,
            "messages": messages,
            "temperature": 0.3,  # Lower temp for more focused reviews
            "max_tokens": 2048,  # Generous limit for detailed reviews
            "stream": False,  # We want complete responses
        }

        # Common parameters for all models
        kwargs_for_litellm = {
            "model": self.config.llm_model,
            "messages": messages,
            "temperature": 0.3,  # Lower temp for more focused reviews
        }

        # Add other common params like frequency_penalty, presence_penalty from config if defined
        if self.config.llm_api_key:
            kwargs_for_litellm["api_key"] = self.config.llm_api_key
        if self.config.llm_api_base:
            kwargs_for_litellm["api_base"] = self.config.llm_api_base
        
        # Conditionally add api_version, primarily for Azure.
        # Some non-Azure models might also accept a generic 'api_version' if provided.
        if self.config.azure_api_version and (self.config.llm_model and "azure" in self.config.llm_model.lower()):
            kwargs_for_litellm["api_version"] = self.config.azure_api_version
        
        # Enforce JSON output if the model supports it (based on model name heuristic)
        # This needs to be robustly checked against LiteLLM's capabilities for each model.
        # For now, a simple heuristic:
        model_lower = self.config.llm_model.lower()
        if "gpt-4" in model_lower or \
           "gpt-3.5-turbo-1106" in model_lower or \
           "claude-3" in model_lower or \
           "gemini-1.5" in model_lower: # Add other known JSON-mode models
            try:
                kwargs_for_litellm["response_format"] = {"type": "json_object"}
                logger.info(f"Requesting JSON object response_format for model {self.config.llm_model}")
            except Exception as e_rf: # Should not happen with LiteLLM's dict param
                 logger.warning(f"Model {self.config.llm_model} might not support 'response_format' via kwargs. Error: {e_rf}")
        
        logger.info(f"Sending request to LLM for file: {file_path}, model: {self.config.llm_model}")
        if logger.isEnabledFor(logging.DEBUG):
            # Avoid logging potentially large messages payload unless DEBUG is on
            debug_kwargs = {k: (v if k != "messages" else "[MESSAGES_TRUNCATED]") for k,v in kwargs_for_litellm.items()}
            logger.debug(f"LiteLLM Request kwargs (messages truncated): {json.dumps(debug_kwargs, indent=2, default=str)}")
            # For very detailed debugging of messages:
            # logger.debug(f"LiteLLM Request messages: {json.dumps(kwargs_for_litellm.get('messages'), indent=2)}")


        llm_response_content: Optional[str] = None
        try:
            response = litellm.completion(**kwargs_for_litellm)
            
            logger.info(f"Raw LLM response object: {response}")
            logger.info(f"Response choices: {response.choices if hasattr(response, 'choices') else 'No choices'}")            
            if hasattr(response, 'choices') and response.choices:
                logger.info(f"First choice message: {response.choices[0].message if hasattr(response.choices[0], 'message') else 'No message'}")            
            if logger.isEnabledFor(logging.DEBUG):
                 logger.debug(f"Raw LLM response object: {response}")

            if response and response.choices and response.choices[0].message and response.choices[0].message.content:
                llm_response_content = response.choices[0].message.content.strip()
            else:
                logger.warning("LLM response structure not as expected or content is missing.")
                return []

            if not llm_response_content:
                logger.warning("LLM returned empty content.")
                return []

            logger.debug(f"LLM response content to parse: {llm_response_content}")
            parsed_response = json.loads(llm_response_content)
            # Handle both direct reviews and wrapped in additionalProperties
            reviews = parsed_response.get("reviews", []) or parsed_response.get("additionalProperties", {}).get("reviews", [])
            
            valid_reviews = []
            for item in reviews:
                if isinstance(item, dict) and "lineNumber" in item and "reviewComment" in item:
                    try:
                        item["lineNumber"] = int(str(item["lineNumber"])) # Ensure it's int
                        item["reviewComment"] = str(item["reviewComment"])
                        valid_reviews.append(item)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid lineNumber or reviewComment type in review item: {item}. Error: {e}")
                else:
                    logger.warning(f"Malformed review item from LLM (expected dict with keys): {item}")
            
            if valid_reviews:
                 logger.info(f"Received {len(valid_reviews)} review suggestions from LLM for {file_path}.")
            else:
                 logger.info(f"No actionable review suggestions received or parsed from LLM for {file_path}.")
            return valid_reviews

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from LLM: {e}")
            if llm_response_content:
                logger.error(f"LLM Raw Response Content that failed parsing: {llm_response_content[:1000]}...") # Log snippet
            return []
        except litellm.exceptions.APIConnectionError as e: # type: ignore
            logger.error(f"LiteLLM API Connection Error: {e}")
            return []
        except litellm.exceptions.RateLimitError as e: # type: ignore
            logger.error(f"LiteLLM Rate Limit Error: {e}")
            # TODO: Consider implementing retry logic here for transient errors like rate limits
            return []
        except litellm.exceptions.APIError as e: # type: ignore
            logger.error(f"LiteLLM API Error (Status: {e.status_code}, Message: {e.message}, Raw Response: {e.response.text if e.response else 'N/A'})")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during LLM review for {file_path}: {e}", exc_info=True)
            return []