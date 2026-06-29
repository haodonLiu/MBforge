"""LangGraph ReAct agent with tool calling and streaming.

Creates a ReAct agent that can use MBForge tools (KB search, molecule lookup, etc.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("mbforge.agent.graph")


_SYSTEM_PROMPT = """You are MBForge Agent, an assistant for molecular science and drug discovery.

You have access to the following tools:
- kb_search: Search the knowledge base for relevant document chunks
- molecule_search: Search for molecules by name, SMILES, or text
- get_document_content: Get text content of document pages
- compute_molecule_properties: Calculate molecular properties (MW, LogP, etc.)
- list_project_documents: List project documents

Rules:
1. Answer concisely and cite specific molecules, documents, or KB results when available.
2. Use tools when the user asks about specific documents, molecules, or projects.
3. For general knowledge questions, answer directly without tool calls.
4. When presenting molecular data, include SMILES and key properties.
"""


def create_agent(llm: Any, tools: list, system_prompt: str = "") -> Any:
    """Create a LangGraph ReAct agent.

    Args:
        llm: LangChain chat model instance
        tools: List of LangChain tool instances
        system_prompt: Custom system prompt (uses default if empty)

    Returns:
        Compiled LangGraph agent
    """
    from langgraph.prebuilt import create_react_agent

    prompt = system_prompt or _SYSTEM_PROMPT
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=prompt,
    )
    return agent


async def stream_agent_response(
    agent: Any,
    messages: list[dict],
    config: dict | None = None,
) -> AsyncIterator[dict]:
    """Stream agent response events.

    Yields:
        Dicts with 'type' field: 'chunk', 'tool_call', 'tool_result', 'done'
    """
    try:
        async for event in agent.astream_events(
            {"messages": messages},
            config=config or {},
            version="v2",
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    content = chunk.content
                    if content:
                        yield {"type": "chunk", "content": content}

            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                yield {"type": "tool_call", "tool": tool_name, "args": event.get("data", {}).get("input", {})}

            elif kind == "on_tool_end":
                output = event.get("data", {}).get("output", "")
                yield {"type": "tool_result", "output": str(output)[:500]}

    except Exception as e:
        logger.error("Agent streaming error: %s", e)
        yield {"type": "error", "error": str(e)}

    yield {"type": "done"}
