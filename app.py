#!/usr/bin/env python3
"""SIS Email Process Suite — Interactive CLI for generating and sending access emails."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
import questionary
from questionary import Style

import config
from config import setup_logging
from services.jira_client import JiraClient, JiraError
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
from services.snow_automation import SnowAutomation, SnowAutomationError

console = Console()

# Questionary style
PROMPT_STYLE = Style([
    ("qmark", "fg:cyan bold"),
    ("question", "fg:white bold"),
    ("answer", "fg:green bold"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan bold"),
    ("selected", "fg:green"),
])


# ---------------------------------------------------------------------------
# Ticket processing pipeline
# ---------------------------------------------------------------------------

def process_ticket(jira: JiraClient, ticket_id: str, snow: SnowAutomation | None) -> dict:
    """Process a single ticket: fetch data, generate email, present options.

    Returns a result dict: {ticket_id, user_name, action, status}
    """
    result = {"ticket_id": ticket_id, "user_name": "", "action": "", "status": ""}

    # 1. Fetch Jira data
    console.print(f"\n[bold cyan]Processing {ticket_id}...[/]")
    try:
        issue = jira.get_issue(ticket_id)
    except JiraError as e:
        console.print(f"[red]Error fetching ticket: {e}[/]")
        result["action"] = "Error"
        result["status"] = str(e)
        return result

    fields = issue["fields"]
    summary = fields.get("summary", "")
    user_name = extract_user_name(summary)
    result["user_name"] = user_name

    # 2. Determine template type
    template_type = determine_template_type(summary)
    if not template_type:
        console.print(f"[yellow]Skipping — summary doesn't match 'new access' or 'modify access': {summary}[/]")
        result["action"] = "Skipped"
        result["status"] = "Not an access ticket"
        return result

    # 3. Parse name and look up incident
    try:
        last_name, first_name = parse_name(user_name)
    except ValueError as e:
        console.print(f"[yellow]Warning: {e} — incident lookup may fail[/]")
        last_name, first_name = user_name, ""

    incident_number = None
    if config.INCIDENT_CSV.exists():
        incident_number = search_incident_csv(str(config.INCIDENT_CSV), last_name, first_name)

    # 4. Fetch and classify subtasks
    try:
        subtasks = jira.get_subtasks_detail(ticket_id)
    except JiraError as e:
        console.print(f"[red]Error fetching subtasks: {e}[/]")
        result["action"] = "Error"
        result["status"] = str(e)
        return result

    granted, pending, denied = classify_subtasks(subtasks, user_name)

    # 5. Build email
    email_text = build_email(template_type, granted, pending, denied)

    # 6. Show metadata
    type_label = "New Access" if template_type == "new_access" else "Modify Access"
    meta_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    meta_table.add_column(style="bold")
    meta_table.add_column()
    meta_table.add_row("Ticket", ticket_id)
    meta_table.add_row("User", user_name)
    meta_table.add_row("Type", type_label)
    meta_table.add_row("Granted", str(len(granted)))
    meta_table.add_row("Pending", str(len(pending)))
    meta_table.add_row("Denied", str(len(denied)))
    if incident_number:
        meta_table.add_row("Incident", incident_number)
    console.print(meta_table)

    # 7. Preview/edit/send loop
    while True:
        console.print(Panel(email_text, title="[bold]Email Preview[/]", border_style="cyan", padding=(1, 2)))

        choices = ["Save to file only", "Copy to clipboard", "Edit email", "Skip this ticket"]
        if snow is not None:
            choices.insert(0, "Send to ServiceNow")

        action = questionary.select(
            "What would you like to do?",
            choices=choices,
            style=PROMPT_STYLE,
        ).ask()

        if action is None:  # User pressed Ctrl+C
            result["action"] = "Cancelled"
            result["status"] = "User cancelled"
            return result

        if action == "Edit email":
            email_text = _edit_text(email_text)
            continue  # Show preview again

        if action == "Save to file only":
            path = save_email(
                user_name, str(config.OUTPUT_FOLDER), email_text, ticket_id, incident_number
            )
            console.print(f"[green]Saved to {path}[/]")
            result["action"] = "Saved"
            result["status"] = path
            return result

        if action == "Copy to clipboard":
            try:
                subprocess.run(
                    ["pbcopy"] if sys.platform == "darwin"
                    else ["clip.exe"] if sys.platform == "win32"
                    else ["xclip", "-selection", "clipboard"],
                    input=email_text.encode(),
                    check=True,
                )
                console.print("[green]Copied to clipboard![/]")
            except (subprocess.CalledProcessError, FileNotFoundError):
                console.print("[red]Failed to copy — clipboard tool not available.[/]")
            continue  # Show preview again

        if action == "Send to ServiceNow":
            success = _send_to_snow(snow, jira, ticket_id, user_name, email_text, incident_number)
            if success:
                # Also save a copy locally
                path = save_email(
                    user_name, str(config.OUTPUT_FOLDER), email_text, ticket_id, incident_number
                )
                result["action"] = "Sent + Saved"
                result["status"] = "Resolved in ServiceNow"
            else:
                result["action"] = "SNOW Error"
                result["status"] = "Check browser"
            return result

        if action == "Skip this ticket":
            result["action"] = "Skipped"
            result["status"] = "User skipped"
            return result


def _edit_text(text: str) -> str:
    """Open text in the user's $EDITOR for editing."""
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", ""))

    if editor:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(text)
            tmp_path = f.name
        try:
            subprocess.run([editor, tmp_path], check=True)
            with open(tmp_path, "r") as f:
                return f.read()
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[yellow]Editor failed. Falling back to inline editing.[/]")
        finally:
            os.unlink(tmp_path)

    # Fallback: inline editing with questionary
    console.print("[dim]Tip: Set $EDITOR to open in your preferred text editor.[/]")
    edited = questionary.text(
        "Edit the email (paste full text):",
        default=text,
        multiline=True,
        style=PROMPT_STYLE,
    ).ask()
    return edited if edited is not None else text


def _send_to_snow(
    snow: SnowAutomation,
    jira: JiraClient,
    ticket_id: str,
    user_name: str,
    email_text: str,
    incident_number: str | None,
) -> bool:
    """Find the incident in ServiceNow, post the email, and resolve it."""
    try:
        if incident_number:
            use_known = questionary.confirm(
                f"Use known incident {incident_number}?",
                default=True,
                style=PROMPT_STYLE,
            ).ask()
            if use_known:
                snow.open_incident(incident_number)
            else:
                incident_number = None

        if not incident_number:
            # Search by user name
            console.print(f"[cyan]Searching ServiceNow for '{user_name}'...[/]")
            incidents = snow.find_incident_by_search(user_name)

            if not incidents:
                console.print("[yellow]No incidents found. Trying last name only...[/]")
                try:
                    last, _ = parse_name(user_name)
                    incidents = snow.find_incident_by_search(last)
                except ValueError:
                    pass

            if not incidents:
                console.print("[red]No matching incidents found in ServiceNow.[/]")
                manual = questionary.text(
                    "Enter incident number manually (or leave blank to skip):",
                    style=PROMPT_STYLE,
                ).ask()
                if manual and manual.strip():
                    snow.open_incident(manual.strip())
                else:
                    return False
            elif len(incidents) == 1:
                inc = incidents[0]
                console.print(f"[green]Found: {inc['number']} — {inc['short_description']}[/]")
                snow.open_incident(inc["number"])
            else:
                # Multiple results — let user pick
                choices = [
                    f"{inc['number']} — {inc['short_description']}"
                    for inc in incidents
                ]
                choices.append("Enter manually")
                choice = questionary.select(
                    "Multiple incidents found. Select one:",
                    choices=choices,
                    style=PROMPT_STYLE,
                ).ask()
                if choice == "Enter manually":
                    manual = questionary.text("Incident number:", style=PROMPT_STYLE).ask()
                    if not manual or not manual.strip():
                        return False
                    snow.open_incident(manual.strip())
                else:
                    inc_num = choice.split(" — ")[0]
                    snow.open_incident(inc_num)

        # Post additional comment (customer visible)
        console.print("[cyan]Posting comment...[/]")
        snow.post_comment(email_text)

        # Resolve
        console.print("[cyan]Resolving incident...[/]")
        snow.resolve_incident()

        console.print("[bold green]Incident resolved successfully![/]")

        # Close the Jira ticket
        try:
            jira.close_issue(ticket_id)
            console.print(f"[bold green]Jira ticket {ticket_id} closed![/]")
        except Exception as e:
            console.print(f"[yellow]SNOW resolved but could not close Jira ticket: {e}[/]")

        return True

    except SnowAutomationError as e:
        console.print(f"[red]ServiceNow automation error: {e}[/]")
        console.print("[yellow]The browser is still open — you can complete the action manually.[/]")
        return False


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------

def action_auto_scan(jira: JiraClient, snow: SnowAutomation | None):
    """Auto-scan for ready tickets using Jira filter."""
    with console.status("[cyan]Scanning Jira for ready tickets...[/]"):
        try:
            ready = scan_ready_tickets(jira, config.JIRA_FILTER_ID)
        except JiraError as e:
            console.print(f"[red]Error scanning: {e}[/]")
            return

    if not ready:
        console.print("[yellow]No ready tickets found.[/]")
        return

    # Display results table
    table = Table(title="Ready Tickets", box=box.ROUNDED, border_style="cyan")
    table.add_column("#", style="dim")
    table.add_column("Ticket ID", style="bold")
    table.add_column("User")
    table.add_column("Type")
    table.add_column("Subtasks", justify="right")
    for i, t in enumerate(ready, 1):
        type_label = "New" if t["template_type"] == "new_access" else "Modify"
        table.add_row(str(i), t["ticket_id"], t["user_name"], type_label, str(t["subtask_count"]))
    console.print(table)

    # Multi-select
    choices = [
        questionary.Choice(
            title=f"{t['ticket_id']} — {t['user_name']}",
            value=t["ticket_id"],
        )
        for t in ready
    ]
    selected = questionary.checkbox(
        "Select tickets to process:",
        choices=choices,
        style=PROMPT_STYLE,
    ).ask()

    if not selected:
        console.print("[dim]No tickets selected.[/]")
        return

    results = _process_ticket_list(jira, selected, snow)
    _show_summary(results)


def action_manual_entry(jira: JiraClient, snow: SnowAutomation | None):
    """Enter ticket IDs manually."""
    raw = questionary.text(
        "Enter ticket IDs (comma or space separated):",
        style=PROMPT_STYLE,
    ).ask()
    if not raw or not raw.strip():
        return

    ticket_ids = [t.strip() for t in raw.replace(",", " ").split() if t.strip()]
    if not ticket_ids:
        console.print("[yellow]No valid ticket IDs entered.[/]")
        return

    console.print(f"[cyan]Processing {len(ticket_ids)} ticket(s)...[/]")
    results = _process_ticket_list(jira, ticket_ids, snow)
    _show_summary(results)


def action_load_from_file(jira: JiraClient, snow: SnowAutomation | None):
    """Load ticket IDs from inputs/tickets.txt."""
    if not config.TICKETS_FILE.exists():
        console.print(f"[red]File not found: {config.TICKETS_FILE}[/]")
        return

    ticket_ids = [
        line.strip()
        for line in config.TICKETS_FILE.read_text().splitlines()
        if line.strip()
    ]

    if not ticket_ids:
        console.print("[yellow]No ticket IDs in file.[/]")
        return

    console.print(f"[cyan]Found {len(ticket_ids)} tickets:[/]")
    for tid in ticket_ids:
        console.print(f"  • {tid}")

    if not questionary.confirm("Process these tickets?", default=True, style=PROMPT_STYLE).ask():
        return

    results = _process_ticket_list(jira, ticket_ids, snow)
    _show_summary(results)


def action_settings(jira: JiraClient):
    """Check configuration and connections."""
    console.print(Panel("[bold]Settings & Configuration[/]", border_style="cyan"))

    settings_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    settings_table.add_column(style="bold")
    settings_table.add_column()
    settings_table.add_row("Jira Server", config.JIRA_SERVER)
    settings_table.add_row("Jira Filter", config.JIRA_FILTER_ID)
    settings_table.add_row("SNOW Instance", config.SNOW_INSTANCE_URL)
    settings_table.add_row("Tickets File", str(config.TICKETS_FILE))
    settings_table.add_row("Incident CSV", str(config.INCIDENT_CSV))
    settings_table.add_row("Output Folder", str(config.OUTPUT_FOLDER))

    token_status = "[green]loaded[/]" if _token_available() else "[red]missing[/]"
    settings_table.add_row("Jira Token", token_status)
    console.print(settings_table)

    # Test Jira connection
    console.print("\n[cyan]Testing Jira connection...[/]", end=" ")
    if jira.test_connection():
        console.print("[green]OK[/]")
    else:
        console.print("[red]FAILED[/]")


def _token_available() -> bool:
    try:
        config.get_jira_token()
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _process_ticket_list(
    jira: JiraClient, ticket_ids: list[str], snow: SnowAutomation | None
) -> list[dict]:
    """Process a list of tickets sequentially, returning results."""
    # Ensure output folder exists
    config.OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    results = []
    for tid in ticket_ids:
        result = process_ticket(jira, tid, snow)
        results.append(result)
    return results


def _show_summary(results: list[dict]):
    """Display a summary table after processing a batch."""
    console.print()
    table = Table(title="Processing Summary", box=box.ROUNDED, border_style="green")
    table.add_column("Ticket", style="bold")
    table.add_column("User")
    table.add_column("Action")
    table.add_column("Status")

    for r in results:
        action_style = {
            "Sent + Saved": "green",
            "Saved": "cyan",
            "Skipped": "dim",
            "Error": "red",
            "SNOW Error": "red",
            "Cancelled": "yellow",
        }.get(r["action"], "white")

        table.add_row(
            r["ticket_id"],
            r["user_name"],
            f"[{action_style}]{r['action']}[/]",
            r["status"],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    setup_logging()

    console.print(
        Panel(
            "[bold cyan]SIS Email Process Suite[/]\n"
            "[dim]Generate and send SIS access notification emails[/]",
            border_style="cyan",
            padding=(1, 4),
        )
    )

    # Initialize Jira client
    try:
        token = config.get_jira_token()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    jira = JiraClient(config.JIRA_SERVER, token)
    snow: SnowAutomation | None = None

    try:
        while True:
            console.print()
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "Auto-scan ready tickets",
                    "Enter ticket IDs manually",
                    "Load tickets from file",
                    "Settings",
                    "Exit",
                ],
                style=PROMPT_STYLE,
            ).ask()

            if action is None or action == "Exit":
                break

            # Lazily start ServiceNow session only when needed
            if action in ("Auto-scan ready tickets", "Enter ticket IDs manually", "Load tickets from file"):
                if snow is None:
                    use_snow = questionary.confirm(
                        "Enable ServiceNow automation? (Opens Chrome browser)",
                        default=False,
                        style=PROMPT_STYLE,
                    ).ask()
                    if use_snow:
                        snow = SnowAutomation(config.SNOW_INSTANCE_URL)
                        console.print("[cyan]Starting browser session — complete SSO login if prompted...[/]")
                        snow.start_session()

            if action == "Auto-scan ready tickets":
                action_auto_scan(jira, snow)
            elif action == "Enter ticket IDs manually":
                action_manual_entry(jira, snow)
            elif action == "Load tickets from file":
                action_load_from_file(jira, snow)
            elif action == "Settings":
                action_settings(jira)

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
    finally:
        if snow:
            snow.close()
        console.print("[dim]Goodbye![/]")


if __name__ == "__main__":
    main()
