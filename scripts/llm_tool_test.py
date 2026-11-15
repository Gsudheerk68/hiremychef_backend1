"""python -m scripts.llm_tool_test"""
from langchain_core.tools import tool

from app.ai.agent.llm import get_llm


@tool
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


msg = get_llm().bind_tools([get_weather]).invoke("What is the weather in Nellore?")
print("tool_calls:", msg.tool_calls)
print("text:", msg.content)
