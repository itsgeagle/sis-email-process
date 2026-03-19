"""Auto-scan Jira for tickets with all subtasks completed."""

import logging

from services.jira_client import JiraClient
from services.email_generator import extract_user_name, determine_template_type

logger = logging.getLogger(__name__)


def scan_ready_tickets(jira: JiraClient, filter_id: str = "32386") -> list[dict]:
    """Find tickets from the Jira filter where ALL subtasks are closed/resolved.

    Returns a list of dicts with:
        ticket_id, summary, user_name, template_type, subtask_count
    """
    logger.info("Scanning Jira filter %s for ready tickets...", filter_id)
    issues = jira.get_filter_results(filter_id)
    ready = []

    for issue in issues:
        ticket_id = issue["key"]
        fields = issue["fields"]
        summary = fields.get("summary", "")
        subtasks = fields.get("subtasks", [])

        # Skip tickets with no subtasks
        if not subtasks:
            logger.debug("Skipping %s — no subtasks", ticket_id)
            continue

        # Check if all subtasks are closed or resolved
        all_done = all(
            st["fields"]["status"]["name"].lower() in ("closed", "resolved")
            for st in subtasks
        )
        if not all_done:
            logger.debug("Skipping %s — not all subtasks complete", ticket_id)
            continue

        template_type = determine_template_type(summary)
        if not template_type:
            logger.debug("Skipping %s — not a new/modify access ticket", ticket_id)
            continue

        user_name = extract_user_name(summary)
        ready.append({
            "ticket_id": ticket_id,
            "summary": summary,
            "user_name": user_name,
            "template_type": template_type,
            "subtask_count": len(subtasks),
        })

    logger.info("Found %d ready tickets out of %d total", len(ready), len(issues))
    return ready
