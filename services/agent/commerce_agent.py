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

**Product Discovery**:
- Use `search_products` to find products
- Show: Name, ID, Price, Rating, Description
- Always show prices in dollars: cents ÷ 100 (e.g., 41116 cents = $411.16)

**Checkout Flow**:
When customer wants to buy a product:

1. **Extract information** from the conversation:
   - Product ID (required)
   - First name, Last name, Email
   - Street address, City, State (2-letter code), Postal code
   - Quantity (default: 1)
   - Country (default: "US")

2. **Call create_checkout immediately** if you have the required info:
   ```
   create_checkout(
     product_id="34507",
     quantity=1,
     buyer_first_name="Shabaz",
     buyer_last_name="Patel",
     buyer_email="shabaz@gmail.com",
     address_line_one="123 Mission St",
     address_city="San Francisco",
     address_state="CA",
     address_country="US",
     address_postal_code="92341"
   )
   ```

3. **Show shipping options** from the checkout response, ask customer to select one

4. **Update checkout** with selected shipping: `update_checkout(session_id, fulfillment_option_id)`

5. **Complete checkout**: `complete_checkout(session_id)` with payment token

**Important Rules**:
- Call create_checkout as soon as you have buyer and address information
- Extract names/email/address from the current message or conversation history
- Only ask for missing information - don't ask for info the customer already provided
- Pass ALL parameters to create_checkout that you have available
- Default quantity=1 and country="US" if not specified
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


# ── Memory integration ─────────────────────────────────────────────────────

# Simple in-memory store (for demo - use Redis/DB for production)
_conversation_memory: dict[str, list[dict]] = {}

def get_memory_client():
    """Get a mem0 client for persistent memory (optional)."""
    try:
        from mem0 import MemoryClient
        api_key = os.getenv("MEM0_API_KEY", "")
        if api_key:
            return MemoryClient(api_key=api_key)
    except Exception:
        pass
    return None


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

    # Build context from conversation history
    context_parts = []
    conversation_key = f"{user_id}:{session_id}" if session_id else user_id

    # Try mem0 first, fall back to in-memory
    if memory:
        try:
            # Search with both user_id AND session_id for better context
            memories = memory.search(
                query=user_message,
                user_id=user_id,
                session_id=session_id,
                limit=5
            )
            if memories and isinstance(memories, list):
                # mem0 returns list of dicts with 'memory' key
                memory_texts = [m.get('memory') for m in memories if m.get('memory')]
                if memory_texts:
                    context_parts.append(f"Previous context:\n" + "\n".join(f"- {m}" for m in memory_texts))
        except Exception:
            pass

    # Fallback: use in-memory conversation history
    if not context_parts and conversation_key in _conversation_memory:
        recent = _conversation_memory[conversation_key][-6:]  # Last 3 turns
        if recent:
            context_text = "\n".join(
                f"{msg['role']}: {msg['content']}" for msg in recent
            )
            context_parts.append(f"Conversation history:\n{context_text}")

    # Build the input with context
    full_input = user_message
    if context_parts:
        full_input = "\n\n".join(context_parts) + f"\n\nCustomer says: {user_message}"

    # Run the agent
    result = await Runner.run(agent, input=full_input)
    response = result.final_output or "I'm sorry, I couldn't process that request."

    # Store in mem0 (correct format: list of strings with context)
    if memory:
        try:
            # Extract key facts from the conversation for mem0
            facts = []

            # Check for customer info
            if "name is" in user_message.lower() or "i'm" in user_message.lower():
                facts.append(user_message)
            if "email" in user_message.lower() and "@" in user_message:
                facts.append(user_message)
            if "address" in user_message.lower() or "ship to" in user_message.lower():
                facts.append(user_message)

            # Always store user message if it contains key info
            if facts:
                memory.add(
                    facts,  # List of strings, not dicts
                    user_id=user_id,
                    session_id=session_id
                )
        except Exception:
            pass

    # Always store in in-memory fallback
    if conversation_key not in _conversation_memory:
        _conversation_memory[conversation_key] = []
    _conversation_memory[conversation_key].append({"role": "user", "content": user_message})
    _conversation_memory[conversation_key].append({"role": "assistant", "content": response})
    # Keep only last 20 messages (10 turns)
    if len(_conversation_memory[conversation_key]) > 20:
        _conversation_memory[conversation_key] = _conversation_memory[conversation_key][-20:]

    return response
