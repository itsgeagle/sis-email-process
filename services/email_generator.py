"""Email generation logic: subtask classification, template filling, and file output.

Classification logic matches the original generate_template.py process_subtasks() exactly.
"""

from __future__ import annotations

import logging
import os
import re

import pandas as pd

from services.templates import NEW_ACCESS_TEMPLATE, MODIFY_ACCESS_TEMPLATE

logger = logging.getLogger(__name__)


def extract_user_name(summary: str) -> str:
    """Extract the user's name from a Jira ticket summary.

    Expects format like 'Request new access for LastName, FirstName'.
    Returns the name portion after 'for', or 'Unknown_User'.
    """
    match = re.search(r"for (.+)", summary, re.IGNORECASE)
    return match.group(1) if match else "Unknown_User"


def parse_name(user_name: str) -> tuple[str, str]:
    """Split 'LastName, FirstName' into (last_name, first_name).

    Raises ValueError if the name doesn't contain a comma.
    """
    parts = user_name.split(", ", 1)
    if len(parts) != 2:
        raise ValueError(f"Expected 'Last, First' format but got: '{user_name}'")
    return parts[0].strip(), parts[1].strip()


def determine_template_type(summary: str) -> str | None:
    """Determine which email template to use based on the ticket summary.

    Returns 'new_access', 'modify_access', or None.
    """
    summary_lower = summary.lower()
    if "new access" in summary_lower:
        return "new_access"
    elif "modify access" in summary_lower:
        return "modify_access"
    return None


def classify_subtasks(
    subtasks: list[dict], user_name: str
) -> tuple[list[str], list[str], list[str]]:
    """Classify subtask roles into granted, pending, and denied.

    This matches the original generate_template.py process_subtasks() logic exactly.

    Args:
        subtasks: List of subtask dicts with keys: summary, status, comments.
                  (status is lowercase, comments is list of lowercase strings)
        user_name: The user name to strip from subtask summaries.

    Returns:
        Tuple of (granted_roles, pending_roles, denied_roles) as lists of role name strings.
    """
    granted = []
    pending = []
    denied = []
    user_name_regex = re.escape(user_name)

    for st in subtasks:
        summary = re.sub(
            f" for {user_name_regex}", "", st["summary"], flags=re.IGNORECASE
        )
        status = st["status"]
        comments = st["comments"]

        if status not in ("closed", "resolved"):
            pending.append(summary)
        elif "other access" in summary.lower():
            if not comments or any(
                keyword in comment
                for keyword in ["no additional"]
                for comment in comments
            ):
                pass
            elif any(
                keyword in comment
                for keyword in ["required", "must"]
                for comment in comments
            ):
                denied.append(summary)
        elif any(
            keyword in comment
            for keyword in ["denied", "does not require", "not granted", "no fa", "no access", "does not need"]
            for comment in comments
        ):
            denied.append(summary)
        elif any(
            keyword in comment
            for keyword in ["duplicate", "already"]
            for comment in comments
        ):
            pass
        else:
            granted.append(summary)

    return granted, pending, denied


def build_email(
    template_type: str,
    granted: list[str],
    pending: list[str],
    denied: list[str],
) -> str:
    """Fill an email template with the classified role sections.

    Section formatting matches the original generate_template.py exactly.
    """
    template = NEW_ACCESS_TEMPLATE if template_type == "new_access" else MODIFY_ACCESS_TEMPLATE

    # These format strings match lines 231-233 of the original generate_template.py exactly
    granted_section = f"\n        You have been granted the following roles:\n        • " + "\n        • ".join(granted) + "\n" if granted else ""
    pending_section = f"\n        We are waiting for approval for:\n        • " + "\n        • ".join(pending) + "\n" if pending else ""
    denied_section = f"\n        The following roles were denied:\n        • " + "\n        • ".join(denied) + "\n" if denied else ""

    return template.format(
        granted_section=granted_section,
        pending_section=pending_section,
        denied_section=denied_section,
    )


def search_incident_csv(csv_path: str, last_name: str, first_name: str) -> str | None:
    """Search for an incident number in the CSV by user name.

    Returns the incident number string, or None if not found.
    """
    try:
        data = pd.read_csv(csv_path, encoding="ISO-8859-1")
    except FileNotFoundError:
        logger.warning("Incident CSV not found at %s", csv_path)
        return None
    except Exception as e:
        logger.warning("Error reading incident CSV: %s", e)
        return None

    search_key = f"{last_name}, {first_name}"
    for _, row in data.iterrows():
        if search_key in str(row.get("short_description", "")):
            return str(row.get("number", ""))
    return None


def save_email(
    user_name: str,
    output_folder: str,
    email_message: str,
    ticket_id: str,
    incident_number: str | None,
) -> str:
    """Save the email to a text file. Returns the file path."""
    os.makedirs(output_folder, exist_ok=True)
    file_name = f"{user_name}.txt".replace(", ", "_").replace(" ", "_")
    file_path = os.path.join(output_folder, file_name)
    with open(file_path, "w") as f:
        f.write(f"{ticket_id}\n")
        f.write(f"{incident_number or 'N/A'}\n\n")
        f.write(email_message)
    logger.info("Email saved to %s", file_path)
    return file_path
