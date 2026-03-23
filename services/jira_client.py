"""Jira REST API wrapper for SIS ticket operations."""

import logging
import requests

logger = logging.getLogger(__name__)


class JiraError(Exception):
    """Raised when a Jira API call fails."""

    def __init__(self, ticket_id: str, status_code: int, message: str = ""):
        self.ticket_id = ticket_id
        self.status_code = status_code
        super().__init__(f"Jira API error for {ticket_id} (HTTP {status_code}): {message}")


class JiraClient:
    """Client for interacting with the Jira REST API v2."""

    def __init__(self, server: str, token: str):
        self.server = server.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get_issue(self, ticket_id: str) -> dict:
        """Fetch a single Jira issue by ticket ID."""
        url = f"{self.server}/rest/api/2/issue/{ticket_id}"
        resp = self.session.get(url)
        if resp.status_code != 200:
            raise JiraError(ticket_id, resp.status_code, resp.text[:200])
        return resp.json()

    def get_subtasks_detail(self, ticket_id: str) -> list[dict]:
        """Fetch full details for all subtasks of a parent ticket.

        Returns a list of dicts, each containing:
            key, summary, status (lowercase), comments (list of lowercase body strings)
        """
        parent = self.get_issue(ticket_id)
        subtasks = parent["fields"].get("subtasks", [])
        results = []
        for st in subtasks:
            subtask_data = self.get_issue(st["key"])
            fields = subtask_data["fields"]
            results.append({
                "key": st["key"],
                "summary": fields["summary"],
                "status": fields["status"]["name"].lower(),
                "comments": [
                    c["body"].lower()
                    for c in fields.get("comment", {}).get("comments", [])
                ],
            })
        return results

    def get_filter_results(self, filter_id: str) -> list[dict]:
        """Fetch issues from a saved Jira filter.

        Uses the filter's JQL via the search endpoint.
        Returns a list of issue dicts (same structure as get_issue).
        """
        # First get the filter definition to extract its JQL
        filter_url = f"{self.server}/rest/api/2/filter/{filter_id}"
        resp = self.session.get(filter_url)
        if resp.status_code != 200:
            raise JiraError(f"filter-{filter_id}", resp.status_code, resp.text[:200])
        jql = resp.json()["jql"]

        # Then search with that JQL
        search_url = f"{self.server}/rest/api/2/search"
        all_issues = []
        start_at = 0
        max_results = 50

        while True:
            resp = self.session.get(search_url, params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
            })
            if resp.status_code != 200:
                raise JiraError(f"search-filter-{filter_id}", resp.status_code, resp.text[:200])
            data = resp.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)
            if start_at + len(issues) >= data.get("total", 0):
                break
            start_at += len(issues)

        return all_issues

    def close_issue(self, ticket_id: str):
        """Transition a Jira issue to 'Close Issue' status."""
        url = f"{self.server}/rest/api/2/issue/{ticket_id}/transitions"

        # Get available transitions
        resp = self.session.get(url)
        if resp.status_code != 200:
            raise JiraError(ticket_id, resp.status_code, resp.text[:200])

        transitions = resp.json().get("transitions", [])
        close_transition = None
        for t in transitions:
            if t["name"].lower() == "close issue":
                close_transition = t
                break

        if not close_transition:
            available = [t["name"] for t in transitions]
            raise JiraError(
                ticket_id, 0,
                f"'Close Issue' transition not available. Available: {available}"
            )

        # Execute the transition
        resp = self.session.post(url, json={"transition": {"id": close_transition["id"]}})
        if resp.status_code not in (200, 204):
            raise JiraError(ticket_id, resp.status_code, resp.text[:200])

        logger.info("Closed Jira ticket %s", ticket_id)

    def test_connection(self) -> bool:
        """Test if the Jira connection is working."""
        try:
            resp = self.session.get(f"{self.server}/rest/api/2/myself")
            return resp.status_code == 200
        except requests.RequestException:
            return False
