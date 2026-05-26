import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def generate_stub(ticket: dict) -> str:
    """
    Generate a Python function stub using Groq LLaMA.
    For the hackathon demo, this can be swapped back to OpenAI gpt-4o/Codex
    to satisfy the Codex usage judging criterion.
    """
    prompt = f'''Generate a Python function stub for this developer ticket.

Ticket ID: {ticket.get("id", "N/A")}
Title: {ticket["title"]}
Description: {ticket["description"]}
Priority: {ticket.get("priority", "P2")}
Assignee: {ticket.get("assignee", "Unassigned")}
Acceptance Criteria: {ticket.get("acceptance_criteria", "Not specified")}

Rules:
- Function name in snake_case derived from the title
- Full type hints on all parameters and return type
- Comprehensive docstring: description, Args, Returns, and ticket metadata (ID, priority, assignee)
- 3 to 5 TODO comments matching the acceptance criteria steps
- End with pass
- Output ONLY valid Python code, no markdown, no backticks, no explanation

Example:
def handle_auth_service_rate_limit(
    request_count: int,
    window_seconds: int = 60,
    max_requests: int = 100
) -> bool:
    """
    Implement rate limiting for the authentication service.

    Auto-generated from sprint sync.
    Ticket: OG-AB123456 | Priority: P1 | Assignee: Ruthvik

    Args:
        request_count: Number of requests in current window
        window_seconds: Rolling window size in seconds
        max_requests: Maximum allowed requests per window

    Returns:
        bool: True if request is allowed, False if rate limited
    """
    # TODO: Implement sliding window counter using Redis or in-memory store
    # TODO: Return 429 response with Retry-After header when limit exceeded
    # TODO: Add per-user and per-IP rate limit tiers
    # TODO: Log all rate limit hits with timestamp and user ID
    pass
'''

    model = "llama-3.3-70b-versatile"
    last_error = None
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior Python developer. Output only clean, valid "
                            "Python code. No markdown fences, no explanation, no preamble."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=800,
                temperature=0.15,
            )
            break
        except Exception as exc:
            last_error = exc
            if "429" in str(exc) or "rate" in str(exc).lower():
                model = "llama-3.1-8b-instant"
    else:
        raise last_error

    code = response.choices[0].message.content.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
    return code


def generate_all_stubs(tickets: list) -> list:
    stubs = []
    for ticket in tickets:
        try:
            stub = generate_stub(ticket)
            stubs.append(
                {
                    "ticket_id": ticket.get("id", ""),
                    "title": ticket["title"],
                    "stub_code": stub,
                }
            )
        except Exception as e:
            stubs.append(
                {
                    "ticket_id": ticket.get("id", ""),
                    "title": ticket["title"],
                    "stub_code": f"# Error generating stub: {e}\npass",
                }
            )
    return stubs
