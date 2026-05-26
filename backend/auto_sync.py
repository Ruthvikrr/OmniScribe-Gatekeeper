import threading
from backend.vault import (
    get_oauth_token, get_sync_settings,
    log_push, get_all_oauth_status
)
from backend.integrations import (
    push_to_notion, push_to_jira,
    push_to_github, push_to_slack
)


def _push_notion(session_id, brief, tickets, results):
    try:
        settings = get_sync_settings("notion")
        if not settings["auto_push"]:
            results["notion"] = {"skipped": True}
            return
        r = push_to_notion(brief, tickets, session_id)
        results["notion"] = r
        log_push(
            session_id, "notion",
            "success" if r.get("success") else "failed",
            f"{len(tickets)} tickets pushed" if r.get("success") else r.get("error",""),
            r.get("url", "")
        )
    except Exception as e:
        results["notion"] = {"success": False, "error": str(e)}
        log_push(session_id, "notion", "error", str(e))


def _push_jira(session_id, tickets, results):
    try:
        settings = get_sync_settings("jira")
        if not settings["auto_push"]:
            results["jira"] = {"skipped": True}
            return
        r = push_to_jira(tickets, session_id)
        results["jira"] = r
        created = r.get("created", [])
        keys = ", ".join(c["key"] for c in created) if created else ""
        log_push(
            session_id, "jira",
            "success" if r.get("success") else "failed",
            f"Created: {keys}" if keys else r.get("error", ""),
            ""
        )
    except Exception as e:
        results["jira"] = {"success": False, "error": str(e)}
        log_push(session_id, "jira", "error", str(e))


def _push_github(session_id, tickets, stubs, results):
    try:
        settings = get_sync_settings("github")
        if not settings["auto_push"]:
            results["github"] = {"skipped": True}
            return
        r = push_to_github(tickets, stubs, session_id)
        results["github"] = r
        created = r.get("created", [])
        urls = [c["url"] for c in created]
        log_push(
            session_id, "github",
            "success" if r.get("success") else "failed",
            f"{len(created)} issues opened",
            urls[0] if urls else ""
        )
    except Exception as e:
        results["github"] = {"success": False, "error": str(e)}
        log_push(session_id, "github", "error", str(e))


def _push_slack(session_id, brief, tickets, results):
    try:
        settings = get_sync_settings("slack")
        if not settings["auto_push"] or not settings["push_brief"]:
            results["slack"] = {"skipped": True}
            return
        r = push_to_slack(brief, tickets, session_id)
        results["slack"] = r
        log_push(
            session_id, "slack",
            "success" if r.get("success") else "failed",
            "Summary posted to channel" if r.get("success") else r.get("error",""),
            ""
        )
    except Exception as e:
        results["slack"] = {"success": False, "error": str(e)}
        log_push(session_id, "slack", "error", str(e))


def auto_deploy(session_id: str, brief: str, tickets: list,
                stubs: list, summary: str) -> dict:
    """
    Push to all connected and auto-push-enabled integrations in parallel.
    Uses threads so slow APIs don't block the UI response.
    Returns results dict once all threads complete.
    """
    connected = get_all_oauth_status()
    results = {}
    threads = []

    if "notion" in connected:
        t = threading.Thread(
            target=_push_notion,
            args=(session_id, summary, tickets, results)
        )
        threads.append(t)

    if "jira" in connected:
        t = threading.Thread(
            target=_push_jira,
            args=(session_id, tickets, results)
        )
        threads.append(t)

    if "github" in connected:
        t = threading.Thread(
            target=_push_github,
            args=(session_id, tickets, stubs, results)
        )
        threads.append(t)

    if "slack" in connected:
        t = threading.Thread(
            target=_push_slack,
            args=(session_id, brief, tickets, results)
        )
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    return results


def build_sync_results_html(results: dict, session_id: str) -> str:
    """
    Build the HTML status bar showing push results for each service.
    Shown inline in the main status area after pipeline completes.
    """
    if not results:
        return ""

    service_meta = {
        "notion": ("📝", "Notion"),
        "jira":   ("🎫", "Jira"),
        "github": ("🐙", "GitHub"),
        "slack":  ("💬", "Slack"),
    }

    cards = ""
    for service, (icon, name) in service_meta.items():
        if service not in results:
            continue
        r = results[service]

        if r.get("skipped"):
            continue

        if r.get("success"):
            bg = "var(--color-background-success)"
            border = "var(--color-border-success)"
            color = "var(--color-text-success)"
            status_icon = "✓"

            detail = ""
            if service == "notion" and r.get("url"):
                detail = f'<a href="{r["url"]}" target="_blank" style="color:var(--color-text-info);font-size:11px">Open in Notion →</a>'
            elif service == "jira":
                keys = " · ".join(c["key"] for c in r.get("created", []))
                detail = f'<span style="font-size:11px;color:var(--color-text-secondary)">{keys}</span>'
            elif service == "github":
                links = " · ".join(
                    f'<a href="{c["url"]}" target="_blank" style="color:var(--color-text-info);font-size:11px">#{c["number"]}</a>'
                    for c in r.get("created", [])
                )
                detail = links
            elif service == "slack":
                detail = '<span style="font-size:11px;color:var(--color-text-secondary)">Posted to channel</span>'
        else:
            bg = "var(--color-background-danger)"
            border = "var(--color-border-danger)"
            color = "var(--color-text-danger)"
            status_icon = "✕"
            detail = f'<span style="font-size:11px;color:var(--color-text-danger)">{r.get("error","Failed")[:60]}</span>'

        cards += f"""
        <div style="
            background:{bg};border:0.5px solid {border};
            border-radius:8px;padding:8px 12px;
            display:flex;align-items:center;justify-content:space-between;gap:8px;
            flex:1;min-width:140px
        ">
            <div style="display:flex;align-items:center;gap:6px">
                <span>{icon}</span>
                <div>
                    <div style="font-size:12px;font-weight:500;color:{color}">{status_icon} {name}</div>
                    <div style="margin-top:1px">{detail}</div>
                </div>
            </div>
        </div>"""

    if not cards:
        return ""

    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif;margin-top:10px">
        <div style="font-size:11px;font-weight:500;color:var(--color-text-secondary);
                    text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">
            Auto-synced to
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">{cards}</div>
    </div>"""
