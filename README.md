# SIS Email Process

Automates the generation and delivery of SIS access notification emails for the Berkeley IT CAD Security Team. Fetches Jira ticket data, classifies subtask roles, generates email templates, and optionally resolves ServiceNow incidents via browser automation.

## Setup

**Requirements:** Python 3.11+, Google Chrome (for ServiceNow automation only)

1. Clone the repo and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values:

   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   |---|---|
   | `JIRA_SERVER` | Jira instance URL |
   | `JIRA_TOKEN` | Jira personal access token (Bearer auth) |
   | `JIRA_FILTER_ID` | Jira filter ID for auto-scan |
   | `SNOW_INSTANCE_URL` | ServiceNow instance URL |

   Alternatively, place your Jira token in `inputs/token.txt`.

3. (Optional) Place a ServiceNow incident export at `inputs/incident.csv` for automatic incident number lookup.

## Usage

Run the interactive CLI:

```bash
python app.py
```

The main menu provides four options:

- **Auto-scan ready tickets** — Queries a Jira filter for tickets where all subtasks are closed/resolved, then lets you select which to process.
- **Enter ticket IDs manually** — Type in one or more SISRP ticket IDs (comma or space separated).
- **Load tickets from file** — Reads ticket IDs from `inputs/tickets.txt` (one per line).
- **Settings** — View current configuration and test the Jira connection.

### Processing a ticket

For each ticket, the tool:

1. Fetches the ticket and its subtasks from Jira
2. Classifies roles as granted, pending, or denied
3. Generates an email from the appropriate template
4. Shows a preview with options to:
   - **Send to ServiceNow** — Posts the email as a work note and resolves the incident (requires Chrome + SSO login)
   - **Save to file** — Writes the email to `filled_templates/`
   - **Copy to clipboard** — Copies the email text for pasting elsewhere
   - **Edit email** — Opens in `$EDITOR` or inline editor for manual changes
   - **Skip** — Move on to the next ticket

## Input Files

All in `inputs/`:

| File | Purpose |
|---|---|
| `token.txt` | Jira personal access token (fallback if `.env` not set) |
| `tickets.txt` | Newline-separated SISRP ticket IDs for batch processing |
| `incident.csv` | ServiceNow export mapping incident numbers to user names |

## Output

Generated emails are saved to `filled_templates/` as text files named by user.
