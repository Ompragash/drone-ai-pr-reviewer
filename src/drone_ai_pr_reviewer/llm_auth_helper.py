import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def setup_liteLLM_provider_specific_env(config: 'PluginConfig') -> bool:
    """
    Sets up environment variables specific to the chosen LLM provider.
    Returns True if setup was successful, False otherwise.
    """
    try:
        # Infer provider from model name
        model_name = config.llm_model.lower() if config.llm_model else ""
        
        if "azure" in model_name:
            os.environ["AZURE_API_KEY"] = config.llm_api_key
            os.environ["AZURE_API_BASE"] = config.azure_api_version
            os.environ["AZURE_API_VERSION"] = config.azure_api_version
        elif "ollama" in model_name:
            # Ollama uses a local API endpoint
            os.environ["OLLAMA_API_BASE"] = config.llm_api_base or "http://localhost:11434"
        else:
            # Default to OpenAI/OpenRouter/Novita
            os.environ["OPENAI_API_KEY"] = config.llm_api_key
            if config.llm_api_base:
                os.environ["OPENAI_API_BASE"] = config.llm_api_base
                
        logger.info(f"Successfully configured LiteLLM for model: {config.llm_model}")
        return True
            
        logger.info(f"Successfully configured LiteLLM for provider: {provider}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up LiteLLM provider: {e}", exc_info=True)
        return False


def validate_llm_config(config: 'PluginConfig') -> bool:
    """
    Validates the LLM configuration based on the provider.
    Returns True if configuration is valid, False otherwise.
    """
    try:
        provider = config.llm_provider.lower()
        
        if not config.llm_api_key:
            logger.error("LLM API key is required")
            return False
            
        if provider == "azure":
            if not config.llm_azure_base_url:
                logger.error("Azure API base URL is required for Azure provider")
                return False
            if not config.llm_azure_version:
                logger.error("Azure API version is required for Azure provider")
                return False
                
        if provider == "ollama":
            if config.llm_ollama_base_url and not config.llm_ollama_base_url.startswith("http"):
                logger.error("Ollama base URL must be a full HTTP/HTTPS URL")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Error validating LLM configuration: {e}", exc_info=True)
        return False