import html
import re
from datetime import datetime

from backend.vault import store_token_mapping

SANITIZATION_PATTERNS = [
    ("PRIVATE_KEY_FULL_BLOCK", r"(?s)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    ("SSH_PRIVATE_KEY", r"(?s)-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----"),
    ("DB_CONN", r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|sqlserver|mssql|cassandra|elasticsearch)://[^\s'\"<>]+"),
    ("DB_PASSWORD", r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://[^:@\s]+:([^:@\s]{4,})@"),
    ("GROQ_API_KEY_ASSIGNMENT", r"(?i)(groq_api_token|groq_api_key)\s*['\"]?\s*[:=]\s*['\"](gsk_[a-zA-Z0-9]{40,80})['\"]"),
    ("OPENAI_ORG_ID", r"(?i)(openai_organization_id|openai_org_id)\s*['\"]?\s*[:=]\s*['\"](org-[a-zA-Z0-9\-_]+)['\"]"),
    ("JSON_SECRET_FALLBACK", r"(?i)['\"](secret|token|passwd|password|key|org_id|signature)['\"]\s*:\s*['\"]([^'\"]+)['\"]"),
    ("OPENAI_API_KEY", r"sk-(?:proj-)?[a-zA-Z0-9\-_]{20,}"),
    ("ANTHROPIC_API_KEY", r"sk-ant-[a-zA-Z0-9\-_]{20,}"),
    ("GROQ_API_KEY", r"gsk_[a-zA-Z0-9]{20,}"),
    ("GOOGLE_API_KEY", r"AIza[0-9A-Za-z\-_]{20,}"),
    ("STRIPE_KEY", r"sk_(?:live|test)_[a-zA-Z0-9]{16,}"),
    ("STRIPE_WEBHOOK_SECRET", r"whsec_[a-zA-Z0-9]{16,}"),
    ("GITHUB_TOKEN", r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    ("AWS_KEY", r"AKIA[0-9A-Z]{16}"),
    ("AWS_SECRET", r"(?i)aws.{0,20}secret.{0,20}[=:]\s*[\"']?([A-Za-z0-9+/]{40})[\"']?"),
    ("JWT_TOKEN", r"eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"),
    ("BEARER_TOKEN", r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*"),
    ("SLACK_TOKEN", r"xox[bpoas]-[0-9a-zA-Z\-]{10,}"),
    ("DISCORD_TOKEN", r"MT[a-zA-Z0-9\-_]{22,24}\.[a-zA-Z0-9\-_]{6}\.[a-zA-Z0-9\-_]{20,}"),
    ("TWILIO_TOKEN", r"SK[0-9a-fA-F]{32}"),
    ("HUGGINGFACE_TOKEN", r"(?i)(hf_transformers_token|hf_token)\s*['\"]?\s*[:=]\s*['\"](hf_[a-zA-Z0-9]{34,50})['\"]"),
    ("COHERE_API_KEY", r"(?i)(cohere_custom_embed|cohere_api_key)\s*['\"]?\s*[:=]\s*['\"](cm[a-zA-Z0-9]{34,50})['\"]"),
    ("RAZORPAY_KEY", r"(?i)Razorpay-Tracking-ID\s*:\s*(rzp_(?:live|test)_[a-zA-Z0-9]{14,24})"),
    ("RAZORPAY_SECRET", r"(?i)Razorpay-Secret-Hash\s*:\s*(rzp_secret_(?:live|test)_[a-zA-Z0-9\-_]+)"),
    ("STR_KEY_VALUE_FALLBACK", r"(?i)['\"]?(token|embed|secret|hash|id|key)['\"]?\s*[:=]\s*['\"]([^'\"\\]+)['\"]"),
    ("EMAIL", r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ("PHONE", r"(?<![A-Za-z0-9_\-])(?:\+91[\s\-]?)?[6-9]\d{9}(?![A-Za-z0-9_\-])|(?<![A-Za-z0-9_\-])\+?[0-9]{1,3}[\s\-]?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{4,5}(?![A-Za-z0-9_\-])"),
    ("IP_ADDR", r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"),
    ("PAN", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    ("AADHAAR", r"\b[2-9][0-9]{3}\s*[0-9]{4}\s*[0-9]{4}\b"),
    ("CREDIT_CARD", r"\b(?:\d[ -]?){13,19}\b"),
    ("YAML_SECRET", r"(?im)^\s*(?:secret|secret_key|jwt_secret|signing_key|vault_key|encryption_key|hmac_key)\s*[=:]\s*[\"']?([^\s\"'<>\n\r]{4,})[\"']?"),
    ("YAML_PASSWORD", r"(?im)^\s*(?:password|passwd|pwd)\s*[=:]\s*[\"']?([^\s\"'<>\n\r]{4,})[\"']?"),
    ("DOTENV_SECRET", r"(?i)^\s*[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|KEY|CREDENTIALS)\s*=\s*[\"']?[^\"'\n\r]+[\"']?\s*$"),
    ("DJANGO_SECRET_KEY", r"django-insecure-[a-zA-Z0-9\-_%+]*"),
    ("BASIC_AUTH", r"(?i)Basic\s+[A-Za-z0-9+\/=]{20,}"),
    ("LOCALHOST", r"\b(?:localhost|127\.0\.0\.1):[0-9]{2,5}\b"),
    ("SQLITE_FILE", r"[\w\-/\\]+?\.(?:db|sqlite|sqlite3)\b"),
    ("PRIVATE_KEY_HEADER", r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
    ("DB_PASSWORD_INLINE", r"(?i)(?:password|pwd|passwd)\s*[:=]\s*['\"]?[^'\"\s]{4,}['\"]?"),
    ("TOKEN_INLINE", r"(?i)(?:api_key|auth_token|access_token|refresh_token|client_secret|app_secret|webhook_secret|signing_secret)\s*[:=]\s*['\"]?[^'\"\s]{8,}['\"]?"),
]

TOKEN_LABELS = {
    "PRIVATE_KEY_FULL_BLOCK": "PRIVATE_KEY",
    "SSH_PRIVATE_KEY": "PRIVATE_KEY",
    "DB_CONN": "DB_CONN",
    "DB_PASSWORD": "DB_PASSWORD",
    "GROQ_API_KEY_ASSIGNMENT": "API_KEY",
    "OPENAI_API_KEY": "API_KEY",
    "OPENAI_ORG_ID": "ORG_ID",
    "JSON_SECRET_FALLBACK": "SECRET",
    "ANTHROPIC_API_KEY": "API_KEY",
    "GROQ_API_KEY": "API_KEY",
    "GOOGLE_API_KEY": "API_KEY",
    "STRIPE_KEY": "STRIPE_KEY",
    "STRIPE_WEBHOOK_SECRET": "STRIPE_SECRET",
    "GITHUB_TOKEN": "GITHUB_TOKEN",
    "AWS_KEY": "AWS_KEY",
    "AWS_SECRET": "AWS_SECRET",
    "JWT_TOKEN": "JWT_TOKEN",
    "BEARER_TOKEN": "BEARER_TOKEN",
    "SLACK_TOKEN": "SLACK_TOKEN",
    "DISCORD_TOKEN": "DISCORD_TOKEN",
    "TWILIO_TOKEN": "TWILIO_TOKEN",
    "HUGGINGFACE_TOKEN": "HUGGINGFACE_TOKEN",
    "COHERE_API_KEY": "COHERE_API_KEY",
    "RAZORPAY_KEY": "RAZORPAY_KEY",
    "RAZORPAY_SECRET": "RAZORPAY_SECRET",
    "STR_KEY_VALUE_FALLBACK": "SECRET",
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "IP_ADDR": "IP_ADDR",
    "PAN": "PAN",
    "AADHAAR": "AADHAAR",
    "CREDIT_CARD": "CARD_NUM",
    "YAML_SECRET": "SECRET",
    "YAML_PASSWORD": "PASSWORD",
    "DOTENV_SECRET": "SECRET",
    "DJANGO_SECRET_KEY": "SECRET",
    "BASIC_AUTH": "BASIC_AUTH",
    "LOCALHOST": "LOCALHOST",
    "SQLITE_FILE": "FILE_PATH",
    "PRIVATE_KEY_HEADER": "PRIVATE_KEY",
    "DB_PASSWORD_INLINE": "PASSWORD",
    "TOKEN_INLINE": "TOKEN",
}

PRIORITY_PATTERNS = [
    "PRIVATE_KEY_FULL_BLOCK",
    "SSH_PRIVATE_KEY",
    "DB_CONN",
    "DB_PASSWORD",
    "GROQ_API_KEY_ASSIGNMENT",
    "OPENAI_ORG_ID",
    "JSON_SECRET_FALLBACK",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "HUGGINGFACE_TOKEN",
    "COHERE_API_KEY",
    "RAZORPAY_KEY",
    "RAZORPAY_SECRET",
    "STR_KEY_VALUE_FALLBACK",
    "JWT_TOKEN",
    "BEARER_TOKEN",
    "YAML_SECRET",
    "YAML_PASSWORD",
]

PATTERNS = {name: re.compile(pattern) for name, pattern in SANITIZATION_PATTERNS}


def _normalize_secret(label: str, value: str) -> tuple[str, str]:
    suffix = ""
    if label == "DB_CONN":
        stripped = value.rstrip(".,;")
        suffix = value[len(stripped) :]
        value = stripped
    return value, suffix


def sanitize(text: str, session_id: str) -> dict:
    """
    Scan text for PII and secret patterns, replace them with typed tokens,
    and store the real values in the local SQLite vault.
    """
    sanitized = text
    token_map = {}
    counters = {}
    redaction_count = 0

    ordered_keys = PRIORITY_PATTERNS + [name for name in PATTERNS if name not in PRIORITY_PATTERNS]

    for pattern_name in ordered_keys:
        pattern = PATTERNS.get(pattern_name)
        if pattern is None:
            continue

        label = TOKEN_LABELS.get(pattern_name, "SECRET")

        def replace_match(match, _label=label):
            nonlocal redaction_count
            matched_text = match.group(0)
            secret_group = match.group(2) if match.lastindex and match.lastindex >= 2 else matched_text
            real_value, suffix = _normalize_secret(_label, secret_group)
            if not real_value or re.search(r"\[[A-Z0-9_]+_\d+\]", real_value):
                return matched_text

            for token, val in token_map.items():
                if val == real_value:
                    return token + suffix

            counters[_label] = counters.get(_label, 0) + 1
            token = f"[{_label}_{counters[_label]}]"
            token_map[token] = real_value
            redaction_count += 1
            store_token_mapping(session_id, token, real_value, _label)
            if secret_group != matched_text:
                return matched_text.replace(secret_group, token, 1)
            return token + suffix

        sanitized = pattern.sub(replace_match, sanitized)

    return {
        "original": text,
        "sanitized": sanitized,
        "token_map": token_map,
        "redaction_count": redaction_count,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
    }


def highlight_diff(original: str, sanitized: str, token_map: dict) -> tuple:
    """
    Return HTML-highlighted before and after text for the privacy proof panel.
    """
    original_html = html.escape(original)
    sanitized_html = html.escape(sanitized)

    for token, real_value in sorted(token_map.items(), key=lambda item: len(item[1]), reverse=True):
        escaped_value = html.escape(real_value)
        escaped_token = html.escape(token)
        original_html = original_html.replace(
            escaped_value,
            (
                '<mark style="background:#fee2e2;color:#991b1b;padding:1px 3px;'
                f'border-radius:3px;font-weight:500">{escaped_value}</mark>'
            ),
        )
        sanitized_html = sanitized_html.replace(
            escaped_token,
            (
                '<mark style="background:#dcfce7;color:#166534;padding:1px 3px;'
                f'border-radius:3px;font-weight:500">{escaped_token}</mark>'
            ),
        )

    return original_html.replace("\n", "<br>"), sanitized_html.replace("\n", "<br>")
