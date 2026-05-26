import re

PATTERNS = {
    "api_key_openai": re.compile(
        r"sk-[a-zA-Z0-9\-_]{20,}"
    ),
    "api_key_openai_proj": re.compile(
        r"sk-proj-[a-zA-Z0-9\-_]{20,}"
    ),
    "api_key_anthropic": re.compile(
        r"sk-ant-[a-zA-Z0-9\-_]{20,}"
    ),
    "api_key_google": re.compile(
        r"AIza[0-9A-Za-z\-_]{35}"
    ),
    "api_key_stripe_live": re.compile(
        r"sk_live_[a-zA-Z0-9]{24,}"
    ),
    "api_key_stripe_test": re.compile(
        r"sk_test_[a-zA-Z0-9]{24,}"
    ),
    "api_key_github": re.compile(
        r"gh[pousr]_[A-Za-z0-9_]{36,}"
    ),
    "api_key_twilio": re.compile(
        r"SK[0-9a-fA-F]{32}"
    ),
    "aws_access_key": re.compile(
        r"AKIA[0-9A-Z]{16}"
    ),
    "aws_secret_key": re.compile(
        r"(?i)aws.{0,20}secret.{0,20}[=:]\s*[\"']?([a-zA-Z0-9+/]{40})[\"']?"
    ),
    "bearer_token": re.compile(
        r"(?i)bearer\s+[a-zA-Z0-9\-_.+/]{16,}"
    ),
    "huggingface_token": re.compile(
        r"(?i)(hf_transformers_token|hf_token)\s*[\"']?\s*[:=]\s*[\"'](hf_[a-zA-Z0-9]{34,50})[\"']"
    ),
    "cohere_api_key": re.compile(
        r"(?i)(cohere_custom_embed|cohere_api_key)\s*[\"']?\s*[:=]\s*[\"'](cm[a-zA-Z0-9]{34,50})[\"']"
    ),
    "razorpay_key": re.compile(
        r"(?i)Razorpay-Tracking-ID\s*:\s*(rzp_(live|test)_[a-zA-Z0-9]{14,24})"
    ),
    "razorpay_secret": re.compile(
        r"(?i)Razorpay-Secret-Hash\s*:\s*(rzp_secret_(live|test)_[a-zA-Z0-9\-_]+)"
    ),
    "private_key_full_block": re.compile(
        r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED |PGP )?PRIVATE KEY-----"
        r"[\s\S]*?"
        r"-----END (?:OPENSSH |RSA |EC |DSA |ENCRYPTED |PGP )?PRIVATE KEY-----",
        re.DOTALL,
    ),
    "private_key_header": re.compile(
        r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"
    ),
    "base64_key_content": re.compile(
        r"\b[A-Za-z0-9+/]{60,}={0,2}\b"
    ),
    "jwt_token": re.compile(
        r"eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"
    ),
    "yaml_secret_value": re.compile(
        r"(?im)^\s*(?:secret|secret_key|jwt_secret|signing_key|vault_key|"
        r"django[\-_](?:insecure[\-_])?secret|encryption_key|hmac_key)"
        r"\s*[=:]\s*[\"']?([^\s\"'<>\n\r]{8,})[\"']?"
    ),
    "yaml_password_quoted": re.compile(
        r"(?im)^\s*(?:password|passwd|pwd)\s*:\s*[\"']([^\"'<>\n\r]{4,})[\"']"
    ),
    "yaml_password_plain": re.compile(
        r"(?im)^\s*(?:password|passwd|pwd)\s*:\s*(?![\"'])([^\s<>\n\r#]{4,})"
    ),
    "yaml_token_value": re.compile(
        r"(?im)^\s*(?:auth_token|access_token|refresh_token|api_token|"
        r"client_secret|app_secret|webhook_secret|signing_secret)"
        r"\s*[=:]\s*[\"']?([a-zA-Z0-9\-_#@$!.]{12,})[\"']?"
    ),
    "code_secret_assignment": re.compile(
        r"(?i)(?:secret_key|api_key|apikey|access_key|auth_key|private_key|"
        r"encryption_key|signing_key|token_secret)\s*[=:]\s*[\"']([^\"'<>\n\r]{8,})[\"']"
    ),
    "code_password_assignment": re.compile(
        r"(?i)(?:password|passwd|pwd)\s*=\s*[\"']([^\"'<>\n\r]{4,})[\"']"
    ),
    "ip_address_v4": re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|(?:\d{1,3}\.){3}\d{1,3})\b"
    ),
    "ip_address_public": re.compile(
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    ),
    "email": re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    ),
    "phone_india": re.compile(
        r"(?<![A-Za-z0-9_\-])(?:\+91[\s\-]?)?[6-9]\d{9}(?![A-Za-z0-9_\-])"
    ),
    "phone_intl": re.compile(
        r"(?<![A-Za-z0-9_\-])\+?1?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}(?![A-Za-z0-9_\-])"
    ),
    "credit_card": re.compile(
        r"\b(?:\d[ \-]?){13,16}\b"
    ),
    "db_connection_string": re.compile(
        r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|mssql|"
        r"cassandra|elasticsearch):\/\/[^\s'\"<>\n\r]+"
    ),
    "db_embedded_password": re.compile(
        r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis):\/\/"
        r"[^:@\s]+:([^:@\s]{4,})@"
    ),
    "slack_token": re.compile(
        r"xox[bpoas]-[0-9a-zA-Z\-]{10,}"
    ),
    "generic_labelled_secret": re.compile(
        r"(?i)(?:key|token|secret|credential|password|passwd)"
        r"\s*[=:]\s*[\"']?([a-zA-Z0-9+/\-_#@$!]{24,})[\"']?"
    ),
    "string_key_value_fallback": re.compile(
        r"(?i)[\"']?(token|embed|secret|hash|id|key)[\"']?\s*[:=]\s*[\"']([^'\"\\]+)[\"']"
    ),
}

TOKEN_LABELS = {
    "api_key_openai": "API_KEY",
    "api_key_openai_proj": "API_KEY",
    "api_key_anthropic": "API_KEY",
    "api_key_google": "API_KEY",
    "api_key_stripe_live": "STRIPE_KEY",
    "api_key_stripe_test": "STRIPE_KEY",
    "api_key_github": "GH_TOKEN",
    "api_key_twilio": "TWILIO_KEY",
    "aws_access_key": "AWS_KEY",
    "aws_secret_key": "AWS_SECRET",
    "bearer_token": "BEARER_TOKEN",
    "huggingface_token": "HUGGINGFACE_TOKEN",
    "cohere_api_key": "COHERE_API_KEY",
    "razorpay_key": "RAZORPAY_KEY",
    "razorpay_secret": "RAZORPAY_SECRET",
    "private_key_full_block": "PRIVATE_KEY",
    "private_key_header": "PRIVATE_KEY",
    "base64_key_content": "KEY_CONTENT",
    "jwt_token": "JWT_TOKEN",
    "yaml_secret_value": "SECRET_KEY",
    "yaml_password_quoted": "PASSWORD",
    "yaml_password_plain": "PASSWORD",
    "yaml_token_value": "AUTH_TOKEN",
    "code_secret_assignment": "SECRET_KEY",
    "code_password_assignment": "PASSWORD",
    "ip_address_v4": "IP_ADDR",
    "ip_address_public": "IP_ADDR",
    "email": "EMAIL",
    "phone_india": "PHONE",
    "phone_intl": "PHONE",
    "credit_card": "CARD_NUM",
    "db_connection_string": "DB_CONN",
    "db_embedded_password": "DB_PASSWORD",
    "slack_token": "SLACK_TOKEN",
    "generic_labelled_secret": "SECRET",
    "string_key_value_fallback": "SECRET",
}

PRIORITY_PATTERNS = [
    "private_key_full_block",
    "db_connection_string",
    "api_key_openai_proj",
    "api_key_anthropic",
    "api_key_github",
    "huggingface_token",
    "cohere_api_key",
    "razorpay_key",
    "razorpay_secret",
    "jwt_token",
    "yaml_secret_value",
    "yaml_password_quoted",
]
