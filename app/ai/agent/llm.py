"""One place to choose the LLM. Switch providers by changing LLM_MODEL in .env."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()


@lru_cache(maxsize=1)
def get_llm():
    model = os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeError("Set LLM_MODEL in .env, e.g. LLM_MODEL=groq:<model-name>")

    kwargs = {"temperature": 0.7}
    if model.startswith("ollama:"):
        kwargs["base_url"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        kwargs["num_ctx"] = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    elif model.startswith("groq:"):
        kwargs["max_retries"] = 3  # back off and retry on 429 rate limits
        kwargs["timeout"] = 60
    return init_chat_model(model, **kwargs)
