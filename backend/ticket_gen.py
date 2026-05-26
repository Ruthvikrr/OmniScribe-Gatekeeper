import json
import os
import uuid

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_dev_tickets",
        "description": "Extract technical tasks from a developer meeting transcript and return structured tickets.",
        "parameters": {
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
                            "assignee": {"type": "string"},
                            "deadline": {"type": "string"},
                            "ticket_type": {
                                "type": "string",
                            },
                            "acceptance_criteria": {"type": "string"},
                        },
                        "required": ["title", "description", "priority", "ticket_type"],
                    },
                },
                "meeting_summary": {"type": "string"},
            },
            "required": ["tickets", "meeting_summary"],
        },
    },
}


def generate_tickets(sanitized_text: str) -> dict:
    """
    Send sanitized transcript to Groq LLaMA via function calling.
    Returns structured tickets and meeting summary.
    """
    last_error = None
    model = "llama-3.3-70b-versatile"
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior engineering lead. Extract ONLY technical action items "
                            "from developer meeting transcripts. Ignore small talk. Focus on system "
                            "changes, bugs, features, and architecture tasks. Each ticket must "
                            "represent one concrete unit of work. Respond by calling the "
                            "generate_dev_tickets function."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Extract tickets from this sanitized meeting transcript:\n\n{sanitized_text}",
                    },
                ],
                tools=[TICKET_TOOL],
                tool_choice={"type": "function", "function": {"name": "generate_dev_tickets"}},
                max_tokens=2000,
                temperature=0.2,
            )
            break
        except Exception as exc:
            last_error = exc
            if "429" in str(exc) or "rate" in str(exc).lower():
                model = "llama-3.1-8b-instant"
    else:
        error_name = type(last_error).__name__ if last_error else "RuntimeError"
        error_message = str(last_error) if last_error else "Unknown Groq ticket generation failure."
        raise RuntimeError(f"{error_name}: {error_message}") from last_error

    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)

    for ticket in result.get("tickets", []):
        ticket["id"] = f"OG-{str(uuid.uuid4())[:8].upper()}"
        if ticket.get("ticket_type") not in {"feature", "bug", "task", "refactor"}:
            ticket["ticket_type"] = "task"
        ticket.setdefault("assignee", "Unassigned")
        ticket.setdefault("deadline", "Not specified")
        ticket.setdefault("acceptance_criteria", "")

    return result
