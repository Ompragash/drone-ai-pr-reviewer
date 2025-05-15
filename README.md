# README.md

# Drone AI PR Reviewer (`drone-ai-pr-reviewer`)

A Drone CI plugin that leverages Large Language Models (LLMs) via [LiteLLM](https://github.com/BerriAI/litellm) (version >= 1.39.2) to provide automated code reviews on your Pull Requests. Get intelligent feedback and suggestions to improve code quality and streamline your development workflow.

## Features

-   Reviews Pull Request diffs using a wide range of LLMs supported by LiteLLM.
-   Provides inline review comments directly on your PRs.
-   Configurable LLM model, parameters, and provider settings.
-   Supports file exclusion patterns.
-   Easy to integrate into your Drone CI pipeline.

## Prerequisites

1.  **SCM Access Token:** An API token for your SCM (e.g., GitHub, GitLab) with permissions to read repository content, read PR/MR details, and post review comments.
2.  **LLM Provider API Key:** An API key for your chosen LLM provider.
3.  **(Optional) Self-Hosted LLM Setup:** If using a self-hosted LLM (like Ollama), ensure it's accessible from your Drone runners.

## Setup in Drone CI

1.  **Add Secrets to Drone:** Store your SCM access token and LLM API key(s) as secrets (e.g., `MY_GITHUB_TOKEN`, `MY_OPENAI_KEY`).
2.  **Update `.drone.yml`:**

    ```yaml
    kind: pipeline
    type: docker
    name: default

    steps:
      - name: checkout
        image: drone/git
        commands:
          - git fetch --all # Important for accurate diffing

      - name: ai-code-review
        image: yourdockerhubuser/drone-ai-pr-reviewer:latest # TODO: Replace with your image
        environment:
          # --- Required ---
          PLUGIN_LLM_MODEL: openai/gpt-4o
          PLUGIN_LLM_API_KEY:
            from_secret: MY_OPENAI_KEY # Your LLM API key secret
          PLUGIN_SCM_TOKEN:
            from_secret: MY_GITHUB_TOKEN # Your SCM token secret

          # --- Examples of Optional Settings ---
          # PLUGIN_LLM_API_BASE: http://my-ollama-server:11434
          # PLUGIN_TEMPERATURE: "0.1"
          # PLUGIN_EXCLUDE_PATTERNS: "*.md,**/*.test.js"
          # PLUGIN_LOG_LEVEL: DEBUG
          # PLUGIN_AZURE_API_VERSION: "2023-07-01-preview" # If using Azure
    ```

## Configuration Parameters

The plugin is configured via environment variables prefixed with `PLUGIN_`.

| Parameter                       | Description                                                                                                                                    | Required / Default                |
| :------------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------- |
| **Core LLM Settings**           |                                                                                                                                                |                                   |
| `PLUGIN_LLM_MODEL`              | The full LiteLLM model string (e.g., `"openai/gpt-4o"`, `"anthropic/claude-3-opus"`, `"ollama/mistral"`).                                    | **Required**                      |
| `PLUGIN_LLM_API_KEY`            | The API key for the LLM provider.                                                                                                              | **Required*** (unless model needs no key) |
| `PLUGIN_LLM_API_BASE`           | Base URL for the LLM API. Needed for Azure, self-hosted models (Ollama), custom HF Endpoints, NVIDIA NIM, etc.                                 | Optional                          |
| **SCM Settings**                |                                                                                                                                                |                                   |
| `PLUGIN_SCM_TOKEN`              | API token for your SCM (GitHub, GitLab, etc.).                                                                                                 | **Required**                      |
| **Optional LLM Parameters**     |                                                                                                                                                |                                   |
| `PLUGIN_TEMPERATURE`            | Controls LLM randomness (e.g., `0.1`-`1.0`).                                                                                                   | Default: `0.2`                    |
| `PLUGIN_MAX_TOKENS`             | Max tokens per LLM response for a chunk.                                                                                                       | Default: `700`                    |
| `PLUGIN_TOP_P`                  | Nucleus sampling parameter.                                                                                                                    | Default: `1.0`                    |
| *(Others: `FREQUENCY_PENALTY`, `PRESENCE_PENALTY`)* | *(If implemented)*                                                                                                           | *(Defaults if implemented)*       |
| **Optional Provider-Specific**  |                                                                                                                                                |                                   |
| `PLUGIN_AZURE_API_VERSION`      | API version for Azure OpenAI (e.g., `"2023-07-01-preview"`).                                                                                   | Required for Azure OpenAI         |
| `PLUGIN_VERTEXAI_PROJECT`       | Google Cloud Project ID for Vertex AI.                                                                                                         | Required for Vertex AI (if not ADC) |
| `PLUGIN_VERTEXAI_LOCATION`      | Google Cloud region for Vertex AI (e.g., `"us-central1"`).                                                                                     | Required for Vertex AI (if not ADC) |
| `PLUGIN_AWS_REGION_NAME`        | AWS region for Bedrock (e.g., `"us-east-1"`).                                                                                                  | Optional (usually from SDK config) |
| **Plugin Behavior**             |                                                                                                                                                |                                   |
| `PLUGIN_INCLUDE_PATTERNS`       | Comma-separated list of git-style patterns for files/paths to include (e.g., `"src/*.py,docs/**"`). Takes precedence over exclude patterns.    | Default: `""` (all files)        |
| `PLUGIN_EXCLUDE_PATTERNS`       | Comma-separated list of git-style patterns for files/paths to exclude (e.g., `"*.json,dist/**"`).                                               | Default: `""` (none)              |
| `PLUGIN_LOG_LEVEL`              | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).                                                                               | Default: `INFO`                   |

### Pattern Matching Notes
- Both include and exclude patterns use git-style pattern matching (e.g., `**/*.py`, `src/*`, `!exclude.txt`)
- Include patterns take precedence over exclude patterns
- If no include patterns are specified, all files are considered for review
- If no exclude patterns are specified, no files are excluded
- Patterns support wildcards (`*`), double wildcards (`**`), and negation (`!`)

*\* `PLUGIN_LLM_API_KEY` is not required for local models like Ollama that are configured without an API key.*

## How It Works
<!-- ... (Keep this section as it was) ... -->
1.  The plugin is triggered on a Pull Request event in your Drone CI pipeline.
2.  It determines the repository details and the base/head SHAs for the diff.
3.  It fetches the diff content from your SCM.
4.  The diff is parsed into individual files and code chunks.
5.  Excluded files are filtered out.
6.  For each relevant code chunk, a prompt is constructed (including PR context and the diff chunk) and sent to the configured LLM via LiteLLM.
7.  The LLM's response (expected in JSON format) is parsed for review suggestions.
8.  Valid suggestions are formatted and posted back to the Pull Request as review comments.

## Prompt Customization
<!-- ... (Keep this section as it was) ... -->
The default prompt is located in `src/drone_ai_pr_reviewer/prompts/default_review_prompt.txt` within the Docker image. To customize the prompt:
1.  Fork this repository.
2.  Modify the `default_review_prompt.txt` file.
3.  Build and push your own Docker image.
4.  Use your custom image in your `.drone.yml`.

## Local Development & Testing
<!-- ... (Keep this section as it was) ... -->
1.  Clone this repository.
2.  Create a `.env` file from `.env.example` and fill in your API keys, SCM token, and local CI simulation variables.
3.  Ensure you have Python 3.8+ installed.
4.  Set up a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate # or venv\Scripts\activate on Windows
    pip install -r requirements.txt
    pip install -e . # Install the package in editable mode
    ```
5.  You can then run the plugin locally using the CLI entry point:
    ```bash
    drone-ai-pr-reviewer
    ```
    This will use the variables from your `.env` file to simulate a run. You'll need a local Git repository (specified by `DRONE_WORKSPACE` or by running from within it) that matches the `DRONE_REPO_LINK` and other PR variables for diffing to work.

## Building the Docker Image
<!-- ... (Keep this section as it was, remember to replace yourdockerhubuser) ... -->
```bash
# Build for a single architecture (e.g., amd64)
docker build -t yourdockerhubuser/drone-ai-pr-reviewer:latest -f docker/Dockerfile .

# For multi-arch builds (recommended):
# Ensure docker buildx is set up: docker buildx create --use mybuilder
docker buildx build --platform linux/amd64,linux/arm64 \
  -t yourdockerhubuser/drone-ai-pr-reviewer:latest \
  -t yourdockerhubuser/drone-ai-pr_reviewer:$(python setup.py --version) \
  --file docker/Dockerfile \
  --push .
```

## Contributing
Contributions are welcome! Please feel free to submit issues or pull requests.

## License
This project is licensed under the Apache License 2.0. See the LICENSE file for details.