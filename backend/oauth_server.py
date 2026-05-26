import os
import json
import secrets
import threading
import webbrowser
from flask import Flask, request, redirect
from requests_oauthlib import OAuth2Session
from backend.vault import save_oauth_token
from dotenv import load_dotenv
load_dotenv()

# Allow HTTP for local OAuth (development only)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

oauth_app = Flask(__name__)
_state_store = {}  # temp store for OAuth state params

REDIRECT_BASE = "http://localhost:7861/auth"

# ── OAuth configs ─────────────────────────────────────────────────────────────

OAUTH_CONFIGS = {
    "notion": {
        "client_id":       os.getenv("NOTION_CLIENT_ID"),
        "client_secret":   os.getenv("NOTION_CLIENT_SECRET"),
        "auth_url":        "https://api.notion.com/v1/oauth/authorize",
        "token_url":       "https://api.notion.com/v1/oauth/token",
        "redirect_uri":    f"{REDIRECT_BASE}/notion/callback",
        "scope":           ["read_content", "update_content", "insert_content"],
        "extra_params":    {"owner": "user"},
    },
    "github": {
        "client_id":       os.getenv("GITHUB_CLIENT_ID"),
        "client_secret":   os.getenv("GITHUB_CLIENT_SECRET"),
        "auth_url":        "https://github.com/login/oauth/authorize",
        "token_url":       "https://github.com/login/oauth/access_token",
        "redirect_uri":    f"{REDIRECT_BASE}/github/callback",
        "scope":           ["repo", "issues"],
        "extra_params":    {},
    },
    "slack": {
        "client_id":       os.getenv("SLACK_CLIENT_ID"),
        "client_secret":   os.getenv("SLACK_CLIENT_SECRET"),
        "auth_url":        "https://slack.com/oauth/v2/authorize",
        "token_url":       "https://slack.com/api/oauth.v2.access",
        "redirect_uri":    f"{REDIRECT_BASE}/slack/callback",
        "scope":           ["chat:write", "channels:read", "channels:history"],
        "extra_params":    {},
    },
    "jira": {
        "client_id":       os.getenv("JIRA_CLIENT_ID"),
        "client_secret":   os.getenv("JIRA_CLIENT_SECRET"),
        "auth_url":        "https://auth.atlassian.com/authorize",
        "token_url":       "https://auth.atlassian.com/oauth/token",
        "redirect_uri":    f"{REDIRECT_BASE}/jira/callback",
        "scope":           ["read:jira-work", "write:jira-work", "read:jira-user", "offline_access"],
        "extra_params":    {"audience": "api.atlassian.com", "prompt": "consent"},
    },
}

# Remove any services that are not configured (no client id present)
OAUTH_CONFIGS = {k: v for k, v in OAUTH_CONFIGS.items() if v.get("client_id")}

# ── Auth initiation routes ────────────────────────────────────────────────────

def build_auth_url(service: str) -> str | None:
    config = OAUTH_CONFIGS.get(service)
    if not config or not config["client_id"]:
        return None

    state = secrets.token_urlsafe(16)
    _state_store[service] = state

    oauth = OAuth2Session(
        client_id=config["client_id"],
        redirect_uri=config["redirect_uri"],
        scope=config["scope"],
        state=state
    )
    auth_url, _ = oauth.authorization_url(
        config["auth_url"],
        **config.get("extra_params", {})
    )
    return auth_url


@oauth_app.route("/connect/<service>")
def connect_service(service: str):
    url = build_auth_url(service)
    if not url:
        return f"{service.capitalize()} not configured. Add {service.upper()}_CLIENT_ID to .env", 400
    return redirect(url)


# ── Callback routes ───────────────────────────────────────────────────────────

@oauth_app.route("/auth/<service>/callback")
def oauth_callback(service: str):
    config = OAUTH_CONFIGS.get(service)
    if not config:
        return "Unknown service", 400

    state = _state_store.get(service)
    oauth = OAuth2Session(
        client_id=config["client_id"],
        redirect_uri=config["redirect_uri"],
        state=state
    )

    try:
        if service == "notion":
            import base64
            import requests as req

            code = request.args.get("code")
            req_state = request.args.get("state")
            if not code or req_state != state:
                raise Exception("Missing authorization code or state parameter mismatch.")

            auth_str = f"{config['client_id']}:{config['client_secret']}"
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

            resp = req.post(
                config["token_url"],
                headers={
                    "Authorization": f"Basic {b64_auth}",
                    "Content-Type": "application/json"
                },
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": config["redirect_uri"]
                }
            )
            if resp.status_code != 200:
                raise Exception(f"Notion token request failed: {resp.text}")

            token = resp.json()
            save_oauth_token(
                service=service,
                access_token=token.get("access_token", ""),
                refresh_token=token.get("refresh_token"),
                scope=token.get("scope", ""),
                extra_data={"workspace_id": token.get("workspace_id")}
            )
        else:
            # Force request.url to match config["redirect_uri"] scheme and domain to avoid localhost vs 127.0.0.1 mismatch
            auth_response = request.url
            config_uri = config["redirect_uri"]
            if "localhost" in config_uri and "127.0.0.1" in auth_response:
                auth_response = auth_response.replace("127.0.0.1", "localhost")
            elif "127.0.0.1" in config_uri and "localhost" in auth_response:
                auth_response = auth_response.replace("localhost", "127.0.0.1")

            token = oauth.fetch_token(
                config["token_url"],
                client_secret=config["client_secret"],
                authorization_response=auth_response,
                include_client_id=True
            )

            # Handle Slack's different token structure
            if service == "slack":
                actual_token = token.get("access_token") or token.get("authed_user", {}).get("access_token")
                bot_token = token.get("access_token", "")
                save_oauth_token(
                    service=service,
                    access_token=bot_token,
                    scope=token.get("scope", ""),
                    extra_data={"team": token.get("team", {}), "bot_user_id": token.get("bot_user_id")}
                )
            elif service == "jira":
                # Jira returns cloud ID separately
                access_token = token.get("access_token", "")
                save_oauth_token(
                    service=service,
                    access_token=access_token,
                    refresh_token=token.get("refresh_token"),
                    scope=token.get("scope", ""),
                    extra_data={}
                )
                # Fetch accessible Jira resources
                import requests as req
                resources = req.get(
                    "https://api.atlassian.com/oauth/token/accessible-resources",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
                ).json()
                if resources:
                    save_oauth_token(
                        service=service,
                        access_token=access_token,
                        refresh_token=token.get("refresh_token"),
                        extra_data={"cloud_id": resources[0].get("id"), "cloud_url": resources[0].get("url")}
                    )
            else:
                save_oauth_token(
                    service=service,
                    access_token=token.get("access_token", ""),
                    refresh_token=token.get("refresh_token"),
                    scope=token.get("scope", ""),
                    extra_data={}
                )

        return f"""
        <html><body style="font-family:system-ui;background:#0f1117;color:#f1f5f9;
                           display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
            <div style="text-align:center">
                <div style="font-size:48px;margin-bottom:16px">✅</div>
                <h2 style="color:#22c55e;margin:0 0 8px">{service.capitalize()} connected</h2>
                <p style="color:#8b9ab0">Connecting you back to OmniScribe...</p>
                <script>
                    setTimeout(function() {{
                        try {{
                            if (window.opener && !window.opener.closed) {{
                                const parentDoc = window.opener.document;
                                let btn = parentDoc.getElementById("refresh-connections-btn");
                                if (btn) {{
                                    if (btn.tagName !== "BUTTON") {{
                                        const subBtn = btn.querySelector("button");
                                        if (subBtn) btn = subBtn;
                                    }}
                                    btn.click();
                                }}
                                window.close();
                            }} else {{
                                window.location.href = "http://127.0.0.1:7860/";
                            }}
                        }} catch (e) {{
                            window.location.href = "http://127.0.0.1:7860/";
                        }}
                    }}, 1500);
                </script>
            </div>
        </body></html>
        """

    except Exception as e:
        return f"""
        <html><body style="font-family:system-ui;background:#0f1117;color:#f1f5f9;
                           display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
            <div style="text-align:center">
                <div style="font-size:48px;margin-bottom:16px">❌</div>
                <h2 style="color:#ef4444">Connection failed</h2>
                <p style="color:#8b9ab0">{str(e)}</p>
            </div>
        </body></html>
        """


@oauth_app.route("/sync-setting/<service>/<int:value>")
def update_sync_setting(service, value):
    from backend.vault import save_sync_setting
    save_sync_setting(service, "auto_push", value)
    return "ok", 200, {"Access-Control-Allow-Origin": "*"}


@oauth_app.route("/delete-session/<session_id>")
def remove_session(session_id):
    from backend.vault import delete_session
    delete_session(session_id)
    return "ok", 200, {"Access-Control-Allow-Origin": "*"}


# ── Server runner ─────────────────────────────────────────────────────────────

def start_oauth_server():
    oauth_app.run(port=7861, debug=False, use_reloader=False)


def run_oauth_server_in_background():
    thread = threading.Thread(target=start_oauth_server, daemon=True)
    thread.start()
