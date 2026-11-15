"""Tests never call the real LLM: they must be fast, free and deterministic, and
they prove the no-key fallbacks work. Set GREENLIGHT_TEST_LLM=1 to allow real calls."""
import os

if os.getenv("GREENLIGHT_TEST_LLM") != "1":
    # load_dotenv() never overrides an existing variable, so this wins over .env
    os.environ["ANTHROPIC_API_KEY"] = ""
