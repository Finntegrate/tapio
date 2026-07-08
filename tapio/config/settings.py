"""Global configuration settings for the migri-assistant application.

This module contains common configuration settings used across different
components of the migri-assistant application, including default directories
for storing crawled and parsed content.
"""

DEFAULT_CONTENT_DIR = "content"

# Default directory paths
DEFAULT_DIRS = {
    "CRAWLED_DIR": "crawled",
    "PARSED_DIR": "parsed",
    "CHROMA_DIR": "chroma_db",
}

DEFAULT_CHROMA_COLLECTION = "tapio_knowledge"
DEFAULT_CRAWLER_TIMEOUT = 30

# Embedding model configuration
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# RAG configuration defaults
DEFAULT_LLM_MODEL = "llama3.2"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_NUM_RESULTS = 5

# LangSmith configuration
DEFAULT_LANGSMITH_PROJECT = "tapio"
LANGSMITH_ENV_VARS = {
    "LANGCHAIN_TRACING_V2": "true",
    "LANGCHAIN_PROJECT": "tapio",
    "LANGSMITH_API_KEY": "",
    "LANGCHAIN_ENDPOINT": "https://api.smith.langchain.com",
}
