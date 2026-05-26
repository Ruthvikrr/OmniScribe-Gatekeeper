import json
import uuid
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from backend.codex_gen import generate_all_stubs
from backend.brief_gen import generate_brief
from backend.oauth_server import run_oauth_server_in_background, connect_service
from backend.integrations import (
    push_to_notion,
    push_to_jira,
    push_to_github,
    push_to_slack,
    get_integration_status,
)
from backend.sanitizer import highlight_diff, sanitize
from backend.auto_sync import auto_deploy, build_sync_results_html
from backend.ticket_gen import generate_tickets
from backend.transcriber import transcribe_audio
from backend.vault import get_vault_contents, log_session

Path("outputs").mkdir(exist_ok=True)
Path("database").mkdir(exist_ok=True)

_last_session = {}

run_oauth_server_in_background()


def run_pipeline(audio_file, raw_text):
    global _last_session
    progress = gr.Progress()
    session_id = str(uuid.uuid4())[:8].upper()
    _last_session = {}

    progress(0.05, desc="Initialising session...")

    if audio_file is not None:
        input_type = "audio"
        progress(0.15, desc="Transcribing audio locally with Whisper...")
        try:
            text = transcribe_audio(audio_file)
        except Exception as e:
            return (
                "",
                "",
                "",
                _err_md(f"Transcription failed: {e}"),
                "",
                _status_html("error", f"Transcription error: {e}"),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )
    elif raw_text and raw_text.strip():
        input_type = "text"
        text = raw_text.strip()
    else:
        return (
            "",
            "",
            "",
            "",
            "",
            _status_html("warning", "Provide an audio file or paste text to begin."),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    import hashlib
    from backend.vault import get_session_by_hash

    input_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    existing_sid = get_session_by_hash(input_hash)
    if existing_sid:
        msg = f"Duplicate input detected! This was already processed in Session {existing_sid}."
        gr.Warning(msg)
        return (
            "", "", "", "", "",
            _status_html("warning", msg),
            gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
        )

    progress(0.35, desc="Running local privacy scan...")
    result = sanitize(text, session_id)
    original_html, sanitized_html = highlight_diff(
        result["original"], result["sanitized"], result["token_map"]
    )

    vault_rows = get_vault_contents(session_id)
    vault_html = _build_vault_html(session_id, vault_rows)

    progress(0.60, desc="Extracting tickets via Groq LLaMA...")
    try:
        ticket_result = generate_tickets(result["sanitized"])
        tickets = ticket_result.get("tickets", [])
        meeting_summary = ticket_result.get("meeting_summary", "")
    except Exception as e:
        return (
            original_html,
            sanitized_html,
            vault_html,
            _err_md(f"Ticket generation failed: {e}"),
            "",
            _status_html("error", f"Step 3 failed: {e}"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    tickets_html = _build_tickets_html(tickets, meeting_summary)

    tickets_file = Path("outputs") / f"tickets_{session_id}.json"
    with open(tickets_file, "w", encoding="utf-8") as f:
        json.dump(ticket_result, f, indent=2)

    progress(0.82, desc="Groq generating function stubs...")
    try:
        stubs = generate_all_stubs(tickets)
    except Exception:
        stubs = []

    brief_content, brief_path = generate_brief(
        result["sanitized"], tickets, meeting_summary, session_id
    )

    tickets_file = Path("outputs") / f"tickets_{session_id}.json"
    stubs_file = Path("outputs") / f"stubs_{session_id}.py"

    stubs_output = ""
    for stub in stubs:
        stubs_output += f"# -- Ticket {stub['ticket_id']} - {stub['title']}\n\n"
        stubs_output += stub["stub_code"] + "\n\n\n"

    if stubs_output:
        with open(stubs_file, "w", encoding="utf-8") as f:
            f.write(stubs_output)

    log_session(session_id, input_type, result["redaction_count"], len(tickets), len(stubs), input_hash=input_hash)

    # ── Auto-sync to connected platforms ─────────────────────────────────────
    progress(0.93, desc="Syncing to connected platforms...")
    push_results = auto_deploy(
        session_id=session_id,
        brief=meeting_summary,
        tickets=tickets,
        stubs=stubs,
        summary=meeting_summary
    )
    sync_html = build_sync_results_html(push_results, session_id)

    _last_session = {
        "session_id": session_id,
        "brief": meeting_summary,
        "tickets": tickets,
        "stubs": stubs,
        "push_results": push_results
    }

    status = _status_html(
        "success",
        f"Session <code>{session_id}</code> &nbsp;·&nbsp; "
        f"<b>{result['redaction_count']}</b> secrets redacted &nbsp;·&nbsp; "
        f"<b>{len(tickets)}</b> tickets &nbsp;·&nbsp; "
        f"<b>{len(stubs)}</b> stubs generated"
    ) + sync_html

    progress(1.0, desc="Complete")
    return (
        original_html,
        sanitized_html,
        vault_html,
        tickets_html,
        stubs_output,
        status,
        gr.update(value=brief_path, visible=True),
        gr.update(value=str(tickets_file), visible=True),
        gr.update(value=str(stubs_file) if stubs_output else None, visible=bool(stubs_output)),
    )


def _status_html(level: str, message: str) -> str:
    colours = {
        "success": ("#0d2b1a", "#22c55e", "#bbf7d0"),
        "error": ("#2b0d0d", "#ef4444", "#fecaca"),
        "warning": ("#2b2000", "#f59e0b", "#fef3c7"),
        "info": ("#0d1a2b", "#4f8ef7", "#bfdbfe"),
    }
    bg, border, text = colours.get(level, colours["info"])
    icons = {"success": "OK", "error": "ERR", "warning": "WARN", "info": "INFO"}
    icon = icons.get(level, "INFO")
    return f"""
    <div style="
        background:{bg};border:1px solid {border};border-radius:8px;
        padding:10px 14px;font-size:13px;color:{text};
        display:flex;align-items:center;gap:8px;margin-top:6px;
        font-family:'Inter',-apple-system,sans-serif;
    ">
        <span style="font-size:11px;font-weight:700;letter-spacing:.04em">{icon}</span>
        <span>{message}</span>
    </div>"""


def _err_md(msg: str) -> str:
    return f'<p style="color:#ef4444;font-size:13px;padding:10px">Error: {msg}</p>'


def _build_vault_html(session_id: str, vault_rows: list) -> str:
    count = len(vault_rows)
    if count == 0:
        body = """
        <div style="text-align:center;padding:32px;color:#4a5568;font-size:13px">
            No secrets detected in this session.
        </div>"""
    else:
        rows_html = ""
        type_colors = {
            "API_KEY": ("#1e3a5f", "#4f8ef7"),
            "DB_CONN": ("#1e2b1e", "#22c55e"),
            "DB_PASSWORD": ("#2b1e1e", "#ef4444"),
            "EMAIL": ("#2b2b1e", "#f59e0b"),
            "PHONE": ("#1e2b2b", "#06b6d4"),
            "IP_ADDR": ("#2b1e2b", "#a78bfa"),
            "PASSWORD": ("#2b1e1e", "#ef4444"),
            "JWT_TOKEN": ("#1e3a5f", "#4f8ef7"),
            "SLACK_TOKEN": ("#1e3a5f", "#4f8ef7"),
        }
        for row in vault_rows:
            token, ttype, ts = row[0], row[1], row[2][:19]
            bg, fg = type_colors.get(ttype, ("#1e2130", "#8b9ab0"))
            rows_html += f"""
            <tr>
                <td style="padding:10px 14px;font-family:monospace;font-size:12px;color:#f1f5f9">{token}</td>
                <td style="padding:10px 14px">
                    <span style="background:{bg};color:{fg};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500">{ttype}</span>
                </td>
                <td style="padding:10px 14px;font-size:12px;color:#8b9ab0">{ts}</td>
                <td style="padding:10px 14px;font-size:12px;color:#22c55e">Local only</td>
            </tr>"""

        body = f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Inter',-apple-system,sans-serif">
            <thead>
                <tr style="border-bottom:1px solid #2a2d3e">
                    <th style="padding:8px 14px;text-align:left;font-size:11px;color:#4a5568;font-weight:500;text-transform:uppercase;letter-spacing:.05em">Token</th>
                    <th style="padding:8px 14px;text-align:left;font-size:11px;color:#4a5568;font-weight:500;text-transform:uppercase;letter-spacing:.05em">Type</th>
                    <th style="padding:8px 14px;text-align:left;font-size:11px;color:#4a5568;font-weight:500;text-transform:uppercase;letter-spacing:.05em">Stored at</th>
                    <th style="padding:8px 14px;text-align:left;font-size:11px;color:#4a5568;font-weight:500;text-transform:uppercase;letter-spacing:.05em">Location</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>"""

    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
            <div>
                <div style="font-size:14px;font-weight:600;color:#f1f5f9">SQLite Vault</div>
                <div style="font-size:12px;color:#4a5568;margin-top:2px">Session {session_id} | Real values stored locally, never sent to OpenAI</div>
            </div>
            <div style="background:#0d2b1a;border:1px solid #22c55e;border-radius:8px;padding:6px 12px;font-size:12px;font-weight:600;color:#22c55e">
                {count} secret{'s' if count != 1 else ''} protected
            </div>
        </div>
        <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;overflow:hidden">
            {body}
        </div>
    </div>"""


def _build_tickets_html(tickets: list, summary: str) -> str:
    if not tickets:
        return '<p style="color:#4a5568;font-size:13px;padding:10px">No tickets generated.</p>'

    priority_cfg = {
        "P1": ("#2b0d0d", "#ef4444", "Critical"),
        "P2": ("#2b1e00", "#f59e0b", "High"),
        "P3": ("#0d1a2b", "#4f8ef7", "Normal"),
    }
    type_icons = {"feature": "+", "bug": "!", "task": ">", "refactor": "~"}

    summary_html = ""
    if summary:
        summary_html = f"""
        <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;padding:14px 16px;margin-bottom:16px">
            <div style="font-size:11px;color:#4a5568;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Meeting summary</div>
            <p style="font-size:13px;color:#8b9ab0;line-height:1.6;margin:0">{summary}</p>
        </div>"""

    cards_html = ""
    for ticket in tickets:
        priority = ticket.get("priority", "P2")
        bg, fg, label = priority_cfg.get(priority, priority_cfg["P2"])
        ticket_type = ticket.get("ticket_type", "task")
        icon = type_icons.get(ticket_type, ">")
        criteria = ticket.get("acceptance_criteria", "")
        criteria_html = ""
        if criteria:
            criteria_html = f"""
            <div style="margin-top:10px;padding-top:10px;border-top:1px solid #2a2d3e">
                <span style="font-size:11px;color:#4a5568;font-weight:500">Done when: </span>
                <span style="font-size:12px;color:#8b9ab0">{criteria}</span>
            </div>"""

        cards_html += f"""
        <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;padding:14px 16px;margin-bottom:10px">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px">
                <div style="display:flex;align-items:center;gap:8px;flex:1">
                    <span style="font-size:14px;color:#4f8ef7">{icon}</span>
                    <span style="font-size:14px;font-weight:600;color:#f1f5f9">{ticket['title']}</span>
                </div>
                <div style="display:flex;gap:6px;flex-shrink:0">
                    <span style="background:{bg};color:{fg};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap">{priority} | {label}</span>
                    <span style="background:#1e2130;color:#8b9ab0;padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap">{ticket_type}</span>
                </div>
            </div>
            <p style="font-size:13px;color:#8b9ab0;line-height:1.6;margin:0 0 8px">{ticket['description']}</p>
            <div style="display:flex;gap:16px;font-size:12px;color:#4a5568">
                <span>{ticket.get('id','')}</span>
                <span>{ticket.get('assignee','Unassigned')}</span>
                <span>{ticket.get('deadline','Not specified')}</span>
            </div>
            {criteria_html}
        </div>"""

    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
            <div style="font-size:14px;font-weight:600;color:#f1f5f9">Generated tickets</div>
            <span style="background:#0d1a2b;border:1px solid #4f8ef7;border-radius:8px;padding:4px 10px;font-size:12px;font-weight:600;color:#4f8ef7">{len(tickets)} tickets</span>
        </div>
        {summary_html}
        {cards_html}
    </div>"""


def _build_deploy_html(results: dict, error: str) -> str:
    if error:
        return f'<p style="color:#ef4444;font-size:13px;padding:10px">{error}</p>'

    status = get_integration_status()
    cards = ""

    integrations = [
        ("notion", "📝", "Notion", "Page created"),
        ("jira", "🎫", "Jira", "Issues created"),
        ("github", "🐙", "GitHub", "Issues opened"),
        ("slack", "💬", "Slack", "Message posted"),
    ]

    for key, icon, name, success_label in integrations:
        if not status[key]:
            bg, border, text = "#1a1d27", "#2a2d3e", "#4a5568"
            detail = "Not configured — add credentials to .env"
            badge = '<span style="background:#1e2130;color:#4a5568;padding:2px 8px;border-radius:10px;font-size:11px">Not set up</span>'
        elif key in results:
            r = results[key]
            if r.get("success"):
                bg, border, text = "#0d2b1a", "#22c55e", "#bbf7d0"
                detail = success_label
                if key == "notion" and r.get("url"):
                    detail = f'<a href="{r["url"]}" target="_blank" style="color:#22c55e">{success_label} → Open in Notion</a>'
                elif key == "jira":
                    keys = ", ".join(c["key"] for c in r.get("created", []))
                    detail = f"{r.get('total',0)} issues: {keys}"
                elif key == "github":
                    links = " · ".join(
                        f'<a href="{c["url"]}" target="_blank" style="color:#22c55e">#{c["number"]}</a>'
                        for c in r.get("created", [])
                    )
                    detail = links or success_label
                badge = '<span style="background:#0d2b1a;color:#22c55e;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">✓ Done</span>'
            else:
                bg, border, text = "#2b0d0d", "#ef4444", "#fecaca"
                detail = r.get("error", "Failed")
                badge = '<span style="background:#2b0d0d;color:#ef4444;padding:2px 8px;border-radius:10px;font-size:11px">Failed</span>'
        else:
            bg, border, text = "#1a1d27", "#2a2d3e", "#8b9ab0"
            detail = "Configured but not deployed yet"
            badge = '<span style="background:#1e2130;color:#8b9ab0;padding:2px 8px;border-radius:10px;font-size:11px">Ready</span>'

        cards += f"""
        <div style="background:{bg};border:1px solid {border};border-radius:10px;
                    padding:12px 14px;display:flex;align-items:center;justify-content:space-between;gap:10px">
            <div style="display:flex;align-items:center;gap:10px">
                <span style="font-size:20px">{icon}</span>
                <div>
                    <div style="font-size:13px;font-weight:600;color:#f1f5f9">{name}</div>
                    <div style="font-size:12px;color:{text};margin-top:2px">{detail}</div>
                </div>
            </div>
            {badge}
        </div>"""

    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif">
        <div style="font-size:11px;font-weight:600;color:#4a5568;text-transform:uppercase;
                    letter-spacing:.06em;margin-bottom:12px">Integration status</div>
        <div style="display:flex;flex-direction:column;gap:8px">{cards}</div>
    </div>"""


def deploy_all(progress=gr.Progress()):
    """Deploy last processed session to all configured integrations."""
    if not _last_session:
        return _build_deploy_html({}, "No session processed yet. Run the pipeline first.")

    results = {}
    status = get_integration_status()

    if status["notion"]:
        progress(0.2, desc="Pushing to Notion...")
        results["notion"] = push_to_notion(
            _last_session.get("brief", ""),
            _last_session.get("tickets", []),
            _last_session.get("session_id", "")
        )

    if status["jira"]:
        progress(0.45, desc="Creating Jira issues...")
        results["jira"] = push_to_jira(
            _last_session.get("tickets", []),
            _last_session.get("session_id", "")
        )

    if status["github"]:
        progress(0.70, desc="Opening GitHub issues...")
        results["github"] = push_to_github(
            _last_session.get("tickets", []),
            _last_session.get("stubs", []),
            _last_session.get("session_id", "")
        )

    if status["slack"]:
        progress(0.90, desc="Posting to Slack...")
        results["slack"] = push_to_slack(
            _last_session.get("brief", ""),
            _last_session.get("tickets", []),
            _last_session.get("session_id", "")
        )

    progress(1.0, desc="Done!")
    return _build_deploy_html(results, None)


def load_history():
    from backend.vault import get_all_sessions, get_push_logs
    sessions = get_all_sessions()
    if not sessions:
        return '<p style="font-size:13px;color:var(--text-secondary);padding:16px">No sessions yet.</p>'

    cards = ""
    for s in sessions:
        sid, itype, redacted, tickets, stubs, created = s
        icon = "🎙" if itype == "audio" else "📝"

        push_logs = get_push_logs(sid)
        push_badges = ""
        for log in push_logs:
            svc, status, detail, url, ts = log
            svc_icons = {"notion":"📝","jira":"🎫","github":"🐙","slack":"💬"}
            svc_icon = svc_icons.get(svc, "🔗")
            color = "var(--accent-green)" if status == "success" else "var(--accent-red)"
            badge = f'<span style="font-size:11px;color:{color}">{svc_icon} {svc}</span>'
            if url:
                badge = f'<a href="{url}" target="_blank" style="font-size:11px;color:var(--accent-blue)">{svc_icon} {svc} →</a>'
            push_badges += badge + "&nbsp;&nbsp;"

        cards += f"""
        <div style="
            background:var(--bg-card);
            border:0.5px solid var(--border);
            border-radius:10px;
            padding:12px 14px;margin-bottom:8px
        ">
            <div style="display:flex;align-items:flex-start;
                        justify-content:space-between;gap:10px">
                <div>
                    <div style="font-size:12px;font-weight:500;
                                color:var(--text-primary);margin-bottom:4px">
                        {icon} Session <code style="font-size:11px">{sid}</code>
                        &nbsp;·&nbsp;
                        <span style="color:var(--accent-green);font-size:11px">
                            {redacted} redacted
                        </span>
                        &nbsp;·&nbsp;
                        <span style="color:var(--text-secondary);font-size:11px">
                            {tickets} tickets · {stubs} stubs
                        </span>
                    </div>
                    <div style="font-size:11px;color:var(--text-secondary)">
                        {(created or '')[:19]}
                    </div>
                </div>
                <div style="font-size:11px;color:var(--text-secondary);
                            text-align:right;flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:8px">
                    <div>
                        {push_badges if push_badges else
                         '<span style="color:var(--text-secondary)">Not synced</span>'}
                    </div>
                    <button onclick="deleteSession('{sid}')" 
                            style="background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.2);
                                   padding:3px 8px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;
                                   transition:all 0.15s"
                            onmouseover="this.style.background='rgba(239,68,68,0.2)';this.style.borderColor='rgba(239,68,68,0.3)'"
                            onmouseout="this.style.background='rgba(239,68,68,0.1)';this.style.borderColor='rgba(239,68,68,0.2)'">
                        Delete
                    </button>
                </div>
            </div>
        </div>"""

    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif">
        <div style="display:flex;align-items:center;justify-content:space-between;
                    margin-bottom:12px">
            <div style="font-size:14px;font-weight:500;
                        color:var(--text-primary)">Session history</div>
            <span style="font-size:12px;color:var(--text-secondary)">
                {len(sessions)} sessions stored locally
            </span>
        </div>
        {cards}
    </div>"""


def handle_delete_session(session_id: str):
    from backend.vault import delete_session
    if session_id:
        delete_session(session_id)
    return load_history(), gr.update(value="")

def handle_sync_toggle(val: str):
    if not val:
        return build_connections_html(), build_sync_settings_html(), gr.update(value="")
    try:
        service, enabled = val.split(":")
        from backend.vault import save_sync_setting
        save_sync_setting(service, "auto_push", int(enabled))
    except Exception:
        pass
    return build_connections_html(), build_sync_settings_html(), gr.update(value="")

def build_connections_html() -> str:
    from backend.vault import get_all_oauth_status

    connected = get_all_oauth_status()
    connect_base_url = "http://127.0.0.1:7861"

    services = [
        ("notion", "📝", "Notion", "Push meeting briefs and tickets as Notion pages"),
        ("github", "🐙", "GitHub", "Create issues with Codex stubs attached"),
        ("slack",  "💬", "Slack",  "Post meeting summaries to your team channel"),
        ("jira",   "🎫", "Jira",   "Auto-create sprint tickets from meetings"),
    ]

    cards = ""
    for key, icon, name, desc in services:
        if key in connected:
            ts = connected[key][:16]
            status_html = f"""
            <span style="background:#0d2b1a;color:#22c55e;border:1px solid #22c55e;
                         padding:3px 10px;border-radius:8px;font-size:11px;font-weight:600">
                ✓ Connected
            </span>
            <span style="font-size:11px;color:#4a5568;margin-left:8px">since {ts}</span>"""
            btn_style = "background:#1e2130;color:#8b9ab0;border:1px solid #2a2d3e"
            btn_label = "Reconnect"
        else:
            status_html = f'<span style="font-size:12px;color:#4a5568">Not connected</span>'
            btn_style = "background:linear-gradient(135deg,#4f8ef7,#3b6fd4);color:#fff;border:none;box-shadow:0 2px 8px rgba(79,142,247,.3)"
            btn_label = f"Connect {name}"

        cards += f"""
        <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;
                    padding:14px 16px;display:flex;align-items:center;
                    justify-content:space-between;gap:12px">
            <div style="display:flex;align-items:center;gap:12px">
                <span style="font-size:24px;width:36px;text-align:center">{icon}</span>
                <div>
                    <div style="font-size:13px;font-weight:600;color:#f1f5f9;margin-bottom:2px">{name}</div>
                    <div style="font-size:12px;color:#4a5568">{desc}</div>
                    <div style="margin-top:4px">{status_html}</div>
                </div>
            </div>
            <button
                onclick="window.open('{connect_base_url}/connect/{key}', '_blank')"
                style="padding:8px 16px;border-radius:8px;font-size:12px;font-weight:600;
                       cursor:pointer;white-space:nowrap;{btn_style}">
                {btn_label}
            </button>
        </div>"""

    total = len(connected)
    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
            <div>
                <div style="font-size:14px;font-weight:600;color:#f1f5f9">Connected integrations</div>
                <div style="font-size:12px;color:#4a5568;margin-top:2px">
                    OAuth tokens stored locally in SQLite — never transmitted
                </div>
            </div>
            <span style="background:#0d1a2b;border:1px solid #4f8ef7;color:#4f8ef7;
                         padding:4px 12px;border-radius:8px;font-size:12px;font-weight:600">
                {total}/4 connected
            </span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px">{cards}</div>
    </div>"""


def build_sync_settings_html() -> str:
    from backend.vault import get_sync_settings, get_all_oauth_status
    connected = get_all_oauth_status()

    services = [
        ("notion", "📝", "Notion"),
        ("jira",   "🎫", "Jira"),
        ("github", "🐙", "GitHub"),
        ("slack",  "💬", "Slack"),
    ]

    rows = ""
    for key, icon, name in services:
        if key not in connected:
            continue
        s = get_sync_settings(key)
        auto = s["auto_push"]
        checked = "checked" if auto else ""
        rows += f"""
        <div style="
            display:flex;align-items:center;justify-content:space-between;
            padding:10px 14px;border-bottom:0.5px solid #2a2d3e
        ">
            <div style="display:flex;align-items:center;gap:10px">
                <span style="font-size:18px">{icon}</span>
                <div>
                    <div style="font-size:13px;font-weight:500;
                                color:#f1f5f9">{name}</div>
                    <div style="font-size:11px;color:#8b9ab0">
                        Auto-push when pipeline completes
                    </div>
                </div>
            </div>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                <span style="font-size:12px;color:#8b9ab0">
                    {"On" if auto else "Off"}
                </span>
                <input type="checkbox" {checked}
                    onchange="toggleSync('{key}', this.checked)"
                    style="width:16px;height:16px;cursor:pointer">
            </label>
        </div>"""

    if not rows:
        return '<p style="font-size:12px;color:#8b9ab0;padding:10px">Connect a service first to configure auto-sync.</p>'

    return f"""
    <div style="font-family:'Inter',-apple-system,sans-serif;margin-top:16px">
        <div style="font-size:11px;font-weight:500;color:#8b9ab0;
                    text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">
            Auto-sync settings
        </div>
        <div style="background:#1a1d27;
                    border:0.5px solid #2a2d3e;
                    border-radius:10px;overflow:hidden">
            {rows}
        </div>
        <p style="font-size:11px;color:#8b9ab0;margin-top:6px">
            When enabled, OmniScribe pushes to this platform automatically
            the moment your pipeline finishes. No extra clicks needed.
        </p>
    </div>"""


CUSTOM_CSS = """
:root {
    --bg-base: #0f1117;
    --bg-card: #1a1d27;
    --bg-card-hover: #1e2130;
    --border: #2a2d3e;
    --border-light: #333650;
    --accent-blue: #4f8ef7;
    --accent-green: #22c55e;
    --accent-amber: #f59e0b;
    --accent-red: #ef4444;
    --text-primary: #f1f5f9;
    --text-secondary: #8b9ab0;
    --text-muted: #4a5568;
    --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

*, *::before, *::after { box-sizing: border-box; }

body, .gradio-container {
    font-family: var(--font) !important;
    background: var(--bg-base) !important;
}

.gradio-container {
    max-width: 1100px !important;
    margin: 0 auto !important;
    padding: 24px !important;
}

.gr-box, .gr-panel, .gr-form, .gr-block {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

textarea, input[type="text"] {
    background: var(--bg-base) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    font-family: var(--font) !important;
    font-size: 13px !important;
    padding: 10px 12px !important;
    transition: border-color .15s !important;
}

textarea:focus, input[type="text"]:focus {
    border-color: var(--accent-blue) !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(79,142,247,.12) !important;
}

button.primary {
    background: linear-gradient(135deg, #4f8ef7 0%, #3b6fd4 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    color: #fff !important;
    font-family: var(--font) !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: .01em !important;
    padding: 11px 20px !important;
    cursor: pointer !important;
    transition: all .15s !important;
    box-shadow: 0 2px 8px rgba(79,142,247,.25) !important;
}

button.primary:hover {
    background: linear-gradient(135deg, #5f9aff 0%, #4a7de0 100%) !important;
    box-shadow: 0 4px 16px rgba(79,142,247,.35) !important;
    transform: translateY(-1px) !important;
}

button.primary:active { transform: translateY(0) !important; }

.tab-nav {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 2px !important;
    display: flex !important;
}

.tab-nav button {
    background: transparent !important;
    border: none !important;
    border-radius: 7px !important;
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 7px 14px !important;
    transition: all .15s !important;
    cursor: pointer !important;
}

.tab-nav button.selected {
    background: #262a3d !important;
    color: var(--text-primary) !important;
}

.tab-nav button:hover:not(.selected) {
    color: var(--text-primary) !important;
    background: var(--bg-card-hover) !important;
}

label span, .gr-label {
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: .04em !important;
}

.gr-file-drop-zone {
    background: var(--bg-base) !important;
    border: 1.5px dashed var(--border) !important;
    border-radius: 10px !important;
    transition: border-color .15s !important;
}

.gr-file-drop-zone:hover {
    border-color: var(--accent-blue) !important;
    background: #0d1525 !important;
}

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-light); }

.gr-code, .cm-editor {
    background: var(--bg-base) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    font-size: 12px !important;
}

.output-html p, .output-html div {
    font-family: var(--font) !important;
    font-size: 13px !important;
    line-height: 1.7 !important;
    color: #cbd5e1 !important;
}

.output-html {
    min-width: 0 !important;
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
}

.output-html, .output-html * {
    white-space: pre-wrap !important;
}

.output-html mark {
    display: inline !important;
}

footer { display: none !important; }
.progress-bar { background: var(--accent-blue) !important; }
hr { border-color: var(--border) !important; }
.prose p { color: var(--text-secondary) !important; font-size: 13px !important; }
.prose h3 { color: var(--text-primary) !important; font-size: 14px !important; }
.prose code {
    background: var(--bg-base) !important;
    color: var(--accent-blue) !important;
    padding: 1px 5px !important;
    border-radius: 4px !important;
    font-size: 12px !important;
}
.invisible-hidden {
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    padding: 0 !important;
    margin: -1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
    white-space: nowrap !important;
    border: 0 !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
"""


HEADER_HTML = """
<div style="
    font-family:'Inter',-apple-system,sans-serif;
    padding: 0 0 20px;
    border-bottom: 1px solid #2a2d3e;
    margin-bottom: 20px;
">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px">
        <div>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
                <img src="/favicon.ico" alt="OmniScribe Logo" style="width:32px;height:32px;border-radius:8px;flex-shrink:0;object-fit:cover;">
                <h1 style="font-size:20px;font-weight:700;color:#f1f5f9;margin:0">OmniScribe Gatekeeper</h1>
            </div>
            <p style="font-size:13px;color:#4a5568;margin:0;padding-left:42px">
                Privacy-first agentic workflow - secrets never leave your machine
            </p>
        </div>
        <div style="display:flex;align-items:center;gap:6px;padding-top:4px;flex-wrap:wrap">
            <span style="background:#0d2b1a;border:1px solid #22c55e;color:#22c55e;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600">Local Whisper</span>
            <span style="background:#0d2b1a;border:1px solid #22c55e;color:#22c55e;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600">Zero-leak</span>
            <span style="background:#0d1a2b;border:1px solid #4f8ef7;color:#4f8ef7;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600">Groq LLaMA</span>
            <span style="background:#2b1e00;border:1px solid #f59e0b;color:#f59e0b;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600">Stub generator</span>
        </div>
    </div>

    <div style="
        display:flex;align-items:center;gap:0;margin-top:18px;
        background:#1a1d27;border:1px solid #2a2d3e;border-radius:8px;
        padding:10px 16px;overflow-x:auto;
    ">
        <div style="text-align:center;min-width:80px">
            <div style="font-size:11px;color:#8b9ab0;font-weight:600">01</div>
            <div style="font-size:10px;color:#8b9ab0;margin-top:2px;font-weight:500">Input</div>
        </div>
        <div style="flex:1;height:1px;background:linear-gradient(90deg,#2a2d3e,#4f8ef7);min-width:20px"></div>
        <div style="text-align:center;min-width:80px">
            <div style="font-size:11px;color:#22c55e;font-weight:600">02</div>
            <div style="font-size:10px;color:#22c55e;margin-top:2px;font-weight:500">Local sanitize</div>
        </div>
        <div style="flex:1;height:1px;background:linear-gradient(90deg,#4f8ef7,#22c55e);min-width:20px"></div>
        <div style="text-align:center;min-width:80px">
            <div style="font-size:11px;color:#22c55e;font-weight:600">03</div>
            <div style="font-size:10px;color:#22c55e;margin-top:2px;font-weight:500">SQLite vault</div>
        </div>
        <div style="flex:1;height:1px;background:linear-gradient(90deg,#22c55e,#f59e0b);min-width:20px"></div>
        <div style="text-align:center;min-width:80px">
            <div style="font-size:11px;color:#4f8ef7;font-weight:600">04</div>
            <div style="font-size:10px;color:#4f8ef7;margin-top:2px;font-weight:500">Groq tickets</div>
        </div>
        <div style="flex:1;height:1px;background:linear-gradient(90deg,#f59e0b,#a78bfa);min-width:20px"></div>
        <div style="text-align:center;min-width:80px">
            <div style="font-size:11px;color:#f59e0b;font-weight:600">05</div>
            <div style="font-size:10px;color:#f59e0b;margin-top:2px;font-weight:500">Python stubs</div>
        </div>
        <div style="flex:1;height:1px;background:linear-gradient(90deg,#a78bfa,#22c55e);min-width:20px"></div>
        <div style="text-align:center;min-width:80px">
            <div style="font-size:11px;color:#22c55e;font-weight:600">06</div>
            <div style="font-size:10px;color:#22c55e;margin-top:2px;font-weight:500">MCP deploy</div>
        </div>
    </div>
</div>
"""

SECTION_LABEL_CSS = "font-size:12px;font-weight:600;color:#8b9ab0;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px"


with gr.Blocks(
    title="OmniScribe Gatekeeper",
    css=CUSTOM_CSS,
    theme=gr.themes.Base(),
) as demo:
    gr.HTML(HEADER_HTML)

    gr.HTML(f'<div style="{SECTION_LABEL_CSS}">Input</div>')

    with gr.Row(equal_height=False):
        with gr.Column(scale=5):
            audio_input = gr.Audio(
                label="Upload meeting audio (.mp3 / .wav / .m4a)",
                type="filepath",
                sources=["upload"],
            )

        with gr.Column(scale=1, min_width=20):
            gr.HTML(
                """
            <div style="
                display:flex;align-items:center;justify-content:center;
                height:100%;color:#2a2d3e;font-size:20px;font-weight:300;
                padding-top:24px
            ">or</div>"""
            )

        with gr.Column(scale=6):
            text_input = gr.Textbox(
                label="Paste raw text / chat logs / meeting notes",
                placeholder='Try: "The API key is sk-abc123 and server IP is 192.168.1.1. Contact dev@company.com..."',
                lines=5,
                max_lines=15,
            )

    process_btn = gr.Button(
        "Process -> Sanitize -> Generate Tickets -> Python Stubs",
        variant="primary",
        size="lg",
    )
    status_out = gr.HTML()

    gr.HTML('<div style="height:1px;background:#2a2d3e;margin:20px 0"></div>')
    gr.HTML(f'<div style="{SECTION_LABEL_CSS}">Output</div>')

    with gr.Tabs():
        with gr.TabItem("Privacy proof"):
            gr.HTML(
                """
            <p style="font-size:12px;color:#4a5568;margin:0 0 12px">
                Side-by-side proof that secrets never reach the cloud.
                Left = original. Right = what OpenAI sees.
            </p>"""
            )
            with gr.Row(equal_height=True):
                with gr.Column():
                    gr.HTML(
                        '<div style="font-size:11px;font-weight:600;color:#ef4444;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Original - secrets highlighted</div>'
                    )
                    original_out = gr.HTML(
                        value='<p style="color:#2a2d3e;font-size:13px;padding:16px">Awaiting input...</p>',
                        elem_classes=["output-html"],
                    )
                with gr.Column():
                    gr.HTML(
                        '<div style="font-size:11px;font-weight:600;color:#22c55e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Sanitized - this is all the AI sees</div>'
                    )
                    sanitized_out = gr.HTML(
                        value='<p style="color:#2a2d3e;font-size:13px;padding:16px">Awaiting input...</p>',
                        elem_classes=["output-html"],
                    )

        with gr.TabItem("Vault"):
            gr.HTML(
                """
            <p style="font-size:12px;color:#4a5568;margin:0 0 12px">
                Real values stored only in your local SQLite database. Nothing here is ever transmitted.
            </p>"""
            )
            vault_out = gr.HTML(
                value='<p style="color:#2a2d3e;font-size:13px;padding:16px">Awaiting input...</p>'
            )

        with gr.TabItem("Tickets"):
            gr.HTML(
                """
            <p style="font-size:12px;color:#4a5568;margin:0 0 12px">
                Structured developer tickets extracted via Groq LLaMA Function Calling.
            </p>"""
            )
            tickets_out = gr.HTML(
                value='<p style="color:#2a2d3e;font-size:13px;padding:16px">Awaiting input...</p>'
            )

        

        with gr.TabItem("Python stubs"):
            gr.HTML(
                """
            <p style="font-size:12px;color:#4a5568;margin:0 0 12px">
                Python function scaffolds auto-generated for each ticket.
                Open your IDE - the structure is already there.
            </p>"""
            )
            stubs_out = gr.Code(
                language="python",
                label="Generated function stubs",
                value="# Stubs will appear here after processing...",
            )

        with gr.TabItem("🔌  Connections"):
            gr.HTML("""
            <p style="font-size:12px;color:#4a5568;margin:0 0 12px">
                Connect your team tools with one click.
                OAuth tokens are stored locally in your SQLite vault — never sent anywhere.
            </p>""")
            refresh_conn_btn = gr.Button("Refresh status", size="sm", elem_id="refresh-connections-btn")
            connections_html = gr.HTML(value="")
            sync_settings_html = gr.HTML(value="")
            
            with gr.Row(elem_classes=["invisible-hidden"]):
                sync_toggle_input = gr.Textbox(elem_id="sync-toggle-input")
            
            sync_toggle_input.change(
                fn=handle_sync_toggle,
                inputs=[sync_toggle_input],
                outputs=[connections_html, sync_settings_html, sync_toggle_input]
            )

            refresh_conn_btn.click(
                fn=lambda: (build_connections_html(), build_sync_settings_html()),
                outputs=[connections_html, sync_settings_html]
            )

        with gr.TabItem("📋  Deploy"):
            gr.HTML('<p style="font-size:12px;color:#4a5568;margin:0 0 12px">Push generated assets to your team tools via MCP integrations.</p>')
            deploy_status = gr.HTML(value=_build_deploy_html({}, None))
            deploy_btn = gr.Button("🚀  Deploy to all configured integrations", variant="primary")
            deploy_btn.click(fn=deploy_all, outputs=[deploy_status])

        with gr.TabItem("🕐  History"):
            gr.HTML('<p style="font-size:12px;color:#4a5568;margin:0 0 12px">Every meeting processed locally. Your full audit trail.</p>')
            with gr.Row(elem_classes=["invisible-hidden"]):
                delete_session_id = gr.Textbox(elem_id="delete-session-id-input")
            
            refresh_btn = gr.Button("Refresh history", size="sm", elem_id="refresh-history-btn")
            history_out = gr.HTML(value="")
            
            refresh_btn.click(fn=load_history, outputs=[history_out])
            delete_session_id.change(
                fn=handle_delete_session,
                inputs=[delete_session_id],
                outputs=[history_out, delete_session_id]
            )

    with gr.Row():
        download_brief = gr.File(label="Download MEETING_BRIEF.md", visible=False)
        download_tickets = gr.File(label="Download tickets.json", visible=False)
        download_stubs = gr.File(label="Download stubs.py", visible=False)

    process_btn.click(
        fn=run_pipeline,
        inputs=[audio_input, text_input],
        outputs=[
            original_out,
            sanitized_out,
            vault_out,
            tickets_out,
            stubs_out,
            status_out,
            download_brief,
            download_tickets,
            download_stubs,
        ],
        show_progress="full",
    )

    def on_load():
        return (
            build_connections_html(),
            build_sync_settings_html(),
            load_history(),
            _build_deploy_html({}, None)
        )

    demo.load(
        fn=on_load,
        outputs=[connections_html, sync_settings_html, history_out, deploy_status],
        js="""
    () => {
        window.deleteSession = function(sid) {
            if (confirm("Are you sure you want to delete session " + sid + "? This will permanently erase all local audit logs and decrypted secrets for this session.")) {
                const textbox = document.querySelector("#delete-session-id-input textarea, #delete-session-id-input input");
                if (textbox) {
                    textbox.value = sid;
                    textbox.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        };

        window.toggleSync = function(service, enabled) {
            const textbox = document.querySelector("#sync-toggle-input textarea, #sync-toggle-input input");
            if (textbox) {
                textbox.value = service + ":" + (enabled ? "1" : "0");
                textbox.dispatchEvent(new Event('input', { bubbles: true }));
            }
        };
    }
    """
    )

    demo.queue(default_concurrency_limit=1)



if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        show_error=True,
    )
