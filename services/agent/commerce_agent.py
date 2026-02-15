"""
Commerce Agent — Built with OpenAI Agents SDK.

Uses function tools for ACP operations (search, checkout, payment)
and mem0 for persistent cross-session memory.
"""

from __future__ import annotations

import os
from typing import Optional

from agents import Agent, Runner, function_tool

from acp_framework.agent import create_commerce_tools


SELLER_URL = os.getenv("SELLER_SERVICE_URL", "http://localhost:8001")
PSP_URL = os.getenv("PSP_SERVICE_URL", "http://localhost:8002")

# ── System prompt ────────────────────────────────────────────────────────

COMMERCE_AGENT_INSTRUCTIONS = """You are a helpful shopping assistant that helps customers find and purchase products.

You have access to a product catalog and can help with the entire purchase flow.

**Product Discovery**:
- Search for products based on customer descriptions
- Show product listings with: Name, ID, Price, Rating, Description
- Format each product consistently for easy scanning

**Checkout Flow** (when customer wants to buy):
1. If you have: product ID, customer name, email, and full shipping address → call `create_checkout` immediately
2. If missing info → ask for what's needed (first name, last name, email, full address with street, city, state, postal code)
3. After checkout created → show fulfillment options and ask which shipping method
4. After fulfillment selected → use `update_checkout` with fulfillment_option_id
5. When ready → use `complete_checkout` with payment token "mock_token"

**Important Guidelines**:
- Always show prices in dollars (divide cents by 100). Example: 2999 cents = $29.99
- Include product ID in every product mention so customers can reference it
- When customer says "buy product X" or "get product X", extract:
  * Product ID (from their message or conversation history)
  * Customer info (name, email, address from their message or memory)
  * Then immediately call `create_checkout` - don't ask again for info they already gave
- Use conversation memory to remember:
  * Customer name and contact details
  * Their address if they provided it
  * Products they showed interest in
  * Their preferences and past interactions
- Be proactive: if customer gave you all info, create the checkout immediately
- Guide step-by-step but don't be repetitive - move forward when you have the data

**Memory Usage**:
- Check memories at the start of each conversation
- Remember: customer preferences, past purchases, shipping address, contact info
- Use this context to provide personalized, efficient service
"""


def create_commerce_agent() -> Agent:
    """Create the main commerce agent with all ACP tools."""
    tools = create_commerce_tools(
        seller_url=SELLER_URL,
        psp_url=PSP_URL,
    )

    agent = Agent(
        name="Commerce Assistant",
        instructions=COMMERCE_AGENT_INSTRUCTIONS,
        tools=tools,
        model="gpt-4o-mini",
    )
    return agent


# ── mem0 integration ─────────────────────────────────────────────────────

def get_memory_client():
    """Get a mem0 client for persistent memory (optional)."""
    # Temporarily disabled - mem0 API requires valid subscription
    # Agent will still work, just without cross-session memory
    # To re-enable: get valid API key from mem0.ai and uncomment below
    return None

    # try:
    #     from mem0 import MemoryClient
    #     api_key = os.getenv("MEM0_API_KEY", "")
    #     if api_key:
    #         return MemoryClient(api_key=api_key)
    # except ImportError:
    #     pass
    # return None


async def run_agent_with_memory(
    user_message: str,
    user_id: str = "default",
    session_id: Optional[str] = None,
) -> str:
    """
    Run the commerce agent with optional mem0 memory.

    Retrieves relevant memories, adds them to context,
    runs the agent, and stores new memories.
    """
    agent = create_commerce_agent()
    memory = get_memory_client()

    # Build context with memories (limit to 3 for speed)
    context_parts = []
    if memory:
        try:
            memories = memory.search(user_message, user_id=user_id, limit=3)
            if memories:
                memory_text = "\n".join(
                    f"- {m.get('memory', '')}" for m in memories[:3] if m.get("memory")
                )
                if memory_text:
                    context_parts.append(
                        f"Previous context:\n{memory_text}"
                    )
        except Exception as e:
            # mem0 is optional, silently fail
            pass

    # Build the input
    full_input = user_message
    if context_parts:
        full_input = "\n\n".join(context_parts) + f"\n\nCustomer says: {user_message}"

    # Run the agent
    result = await Runner.run(agent, input=full_input)
    response = result.final_output or "I'm sorry, I couldn't process that request."

    # Store the interaction in memory (async, don't block response)
    if memory:
        try:
            # Fire and forget - don't await to speed up response
            memory.add(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response},
                ],
                user_id=user_id,
            )
        except Exception:
            pass

    return response
