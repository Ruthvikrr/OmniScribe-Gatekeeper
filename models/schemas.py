from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    assignee: Optional[str] = "Unassigned"
    deadline: Optional[str] = "Not specified"
    ticket_type: str
    acceptance_criteria: Optional[str] = ""


class CodeStub(BaseModel):
    ticket_id: str
    function_name: str
    stub_code: str


class SanitizationResult(BaseModel):
    original_text: str
    sanitized_text: str
    token_map: dict
    redaction_count: int
    session_id: str
    timestamp: str


class SessionLog(BaseModel):
    session_id: str
    timestamp: str
    input_type: str
    redaction_count: int
    tickets_generated: int
    stubs_generated: int
