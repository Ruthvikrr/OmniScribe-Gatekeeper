from datetime import datetime
from pathlib import Path


def generate_brief(sanitized_text: str, tickets: list, summary: str, session_id: str) -> str:
    """
    Generate a MEETING_BRIEF.md from the meeting content.
    No API call needed — build it from existing ticket data + summary.
    """
    lines = []
    lines.append("# Meeting Brief")
    lines.append(f"\n**Session:** `{session_id}`  ")
    lines.append(f"**Generated:** {datetime.now().strftime('%d %b %Y, %I:%M %p')}  ")
    lines.append("**Processed by:** OmniScribe Gatekeeper — Zero-leak pipeline\n")
    lines.append("---\n")
    lines.append("## Summary\n")
    lines.append(summary + "\n")
    lines.append("---\n")
    lines.append("## Action Items\n")

    for ticket in tickets:
        priority = ticket.get("priority", "P2")
        icon = {"P1": "🔴", "P2": "🟠", "P3": "🟡"}.get(priority, "⚪")
        lines.append(f"### {icon} [{ticket.get('id', '')}] {ticket['title']}")
        lines.append(f"- **Priority:** {priority}  ")
        lines.append(f"- **Type:** {ticket.get('ticket_type', 'task')}  ")
        lines.append(f"- **Assignee:** {ticket.get('assignee', 'Unassigned')}  ")
        lines.append(f"- **Deadline:** {ticket.get('deadline', 'Not specified')}  ")
        lines.append(f"\n{ticket['description']}\n")
        if ticket.get("acceptance_criteria"):
            lines.append(f"**Done when:** {ticket['acceptance_criteria']}\n")

    lines.append("---\n")
    lines.append("## Privacy & Security\n")
    lines.append("This document was generated from a sanitized transcript.")
    lines.append("No secrets, API keys, or PII were transmitted to any cloud service.")
    lines.append("All redacted values are stored locally in `database/vault.db`.\n")

    content = "\n".join(lines)

    out_path = Path("outputs") / f"MEETING_BRIEF_{session_id}.md"
    out_path.write_text(content, encoding="utf-8")
    return content, str(out_path)
