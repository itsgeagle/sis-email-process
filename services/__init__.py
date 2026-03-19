"""Service modules for the SIS Email Process suite."""

from services.jira_client import JiraClient, JiraError
from services.snow_automation import SnowAutomation, SnowAutomationError
from services.email_generator import (
    extract_user_name,
    parse_name,
    determine_template_type,
    classify_subtasks,
    build_email,
    search_incident_csv,
    save_email,
)
from services.scanner import scan_ready_tickets
from services.templates import NEW_ACCESS_TEMPLATE, MODIFY_ACCESS_TEMPLATE

__all__ = [
    "JiraClient",
    "JiraError",
    "SnowAutomation",
    "SnowAutomationError",
    "extract_user_name",
    "parse_name",
    "determine_template_type",
    "classify_subtasks",
    "build_email",
    "search_incident_csv",
    "save_email",
    "scan_ready_tickets",
    "NEW_ACCESS_TEMPLATE",
    "MODIFY_ACCESS_TEMPLATE",
]
