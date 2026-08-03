"""Defaults owned by the Tapio application service."""

import os

DEFAULT_CHROMA_COLLECTION = "tapio_knowledge"
DEFAULT_VECTORSTORE_DIR = os.environ.get("TAPIO_VECTORSTORE_DIR", "../vectorstore")
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_LLM_MODEL = "gemma4:latest"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_NUM_RESULTS = 5
