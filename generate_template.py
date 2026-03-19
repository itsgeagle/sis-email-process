import warnings
warnings.warn(
    "This module is deprecated. Use 'python app.py' instead (see email_generator.py, jira_client.py).",
    DeprecationWarning,
    stacklevel=1,
)

import requests
import os
import re
import pandas as pd

def read_token(file_path):
    """Read the personal access token from a file."""
    with open(file_path, 'r') as file:
        return file.read().strip()

def get_jira_data(ticket_id, jira_server, headers):
    """Fetch Jira data for a given ticket ID."""
    jira_issue_url = f'{jira_server}/rest/api/2/issue/{ticket_id}'
    response = requests.get(jira_issue_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch the issue {ticket_id}. Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return None

def extract_user_name(summary):
    """Extract the user's name from the task summary."""
    match = re.search(r'for (.+)', summary, re.IGNORECASE)
    return match.group(1) if match else "Unknown_User"

def determine_template(summary):
    """Select the appropriate email template based on the task summary."""
    if "new access" in summary:
        return """
Hello,

You now have been granted access to UC Berkeley’s Student Information Systems...
"""
    elif "modify access" in summary:
        return """
Hello,

Your SIS account has been updated; added to your existing roles are the requested role(s) below...
"""
    else:
        print("Task summary does not match 'new access' or 'modify access'")
        return None

def process_subtasks(subtasks, jira_server, headers, user_name):
    """Process each subtask and categorize them into granted, pending, or denied roles."""
    granted_roles = []
    pending_roles = []
    denied_roles = []
    user_name_regex = re.escape(user_name)

    for subtask in subtasks:
        subtask_url = f"{jira_server}/rest/api/2/issue/{subtask['key']}"
        subtask_response = requests.get(subtask_url, headers=headers)

        if subtask_response.status_code == 200:
            subtask_data = subtask_response.json()
            subtask_summary = subtask_data['fields']['summary']
            subtask_summary = re.sub(f" for {user_name_regex}", "", subtask_summary, flags=re.IGNORECASE)
            subtask_status = subtask_data['fields']['status']['name'].lower()
            comments = subtask_data['fields']['comment']['comments']
            comments_text = [comment['body'].lower() for comment in comments]
            print(subtask_summary)

            if subtask_status not in ('closed', 'resolved'):
                # print("task open")
                pending_roles.append(subtask_summary)
            elif "other access" in subtask_summary.lower():
                if not comments or any(keyword in comment for keyword in ["no additional"] for comment in comments_text):
                    # print("empty other")
                    pass
                elif any(keyword in comment for keyword in ["required", "must"] for comment in comments_text):
                    # print("denied other")
                    denied_roles.append(subtask_summary)
            elif any(keyword in comment for keyword in ["denied", "does not require", "not granted", "no fa", "no access", "does not need"] for comment in comments_text):
                # print("standard denied")
                denied_roles.append(subtask_summary)
            elif any(keyword in comment for keyword in ["duplicate", "already"] for comment in comments_text):
                # print("redundant request")
                pass
            else:
                # print("granted")
                granted_roles.append(subtask_summary)
            print("pending", pending_roles)
            print("granted", granted_roles)
            print("denied", denied_roles)
        else:
            print(f"Failed to fetch subtask {subtask['key']}. Status Code: {subtask_response.status_code}")

    return granted_roles, pending_roles, denied_roles

def search_incident_csv(csv_path, last_name, first_name):
    """Search for the incident number in the CSV file based on the user's name."""
    try:
        # Use ISO-8859-1 encoding to handle non-UTF-8 characters
        incident_data = pd.read_csv(csv_path, encoding="ISO-8859-1")
    except UnicodeDecodeError as e:
        print(f"Encoding error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

    # Search logic
    for index, row in incident_data.iterrows():
        if f"{last_name}, {first_name}" in row.get("short_description", ""):
            return row.get("number", "Unknown_Incident")
    return "Incident number not found"


def determine_template(summary):
    """Select the appropriate email template based on the task summary."""
    if "new access" in summary:
        return """
Hello,

You now have been granted access to UC Berkeley’s Student Information Systems. This access is based on a request submitted to the Campus Applications & Data (CAD) security team. Please note that your access is based on your position and duties at UC Berkeley and is subject to periodic review.

An employee event or change in job duties will trigger a review and potential loss of some or all currently assigned roles/access. In order to regain access to roles or access thereafter, you will need to complete a new Access Request form.

{granted_section}{pending_section}{denied_section}

Please select SIS Campus Solutions or paste the following URL into your address bar:
https://bcsint.is.berkeley.edu

In the event of any login issues:

• Please clear your browser cache before logging in to SIS Campus Solutions by following these instructions: https://www.wikihow.com/Clear-Your-Browser%27s-Cache
• Logging directly into Campus Solutions now requires the use of a Virtual Private Network (VPN). Please see the following pages for more information: 
- https://security.berkeley.edu/services/bsecure/bsecure-remote-access-vpn
- https://calnetweb.berkeley.edu/calnet-technologists/duo-mfa-service-non-web-integrations

Note:
If you have difficulty accessing SIS or have questions about your access, do not reply to this email as it is not monitored. Please reply to the ServiceNow ticket being created for this request.

Please contact Student Information Systems by replying to the ServiceNow ticket created for this request.

Thanks,
CAD Security Team
"""
    elif "modify access" in summary:
        return """
Hello,

Your SIS account has been updated; added to your existing roles are the requested role(s) below:

{granted_section}{pending_section}{denied_section}

An employee event or change in job duties will trigger a review and potential loss of some or all currently assigned roles/access. In order to regain access to roles or access thereafter, you will need to complete a new Access Request form.

Please select SIS Campus Solutions or paste the following URL into your address bar:
https://bcsint.is.berkeley.edu

In the event of any login issues:

• Please clear your browser cache before logging in to SIS Campus Solutions by following these instructions: https://www.wikihow.com/Clear-Your-Browser%27s-Cache
• Logging directly into Campus Solutions now requires the use of a Virtual Private Network (VPN). Please see the following pages for more information: 
- https://security.berkeley.edu/services/bsecure/bsecure-remote-access-vpn
- https://calnetweb.berkeley.edu/calnet-technologists/duo-mfa-service-non-web-integrations
a
Note:
If you have difficulty accessing SIS or have questions about your access, do not reply to this email as it is not monitored. Please reply to the ServiceNow ticket being created for this request.

Please contact Student Information Systems by replying to the ServiceNow ticket created for this request.

Thanks,
CAD Security Team
"""
    else:
        print("Task summary does not match 'new access' or 'modify access'")
        return None


def save_email_message(user_name, output_folder, email_message, ticket_id, incident_number):
    """Save the email message to a text file named after the user's name."""
    file_name = f"{user_name}.txt".replace(", ", "_").replace(" ", "_")
    file_path = os.path.join(output_folder, file_name)
    with open(file_path, 'w') as file:
        # Add the ticket ID and incident number at the top
        file.write(f"{ticket_id}\n")
        file.write(f"{incident_number}\n\n")
        file.write(email_message)
    print(f"Email message for {user_name} saved to {file_path}")


def generate_template(ticket_id, output_folder):
    # Configuration
    print(ticket_id)
    token_file = 'inputs/token.txt'
    jira_server = 'https://jira-secure.berkeley.edu'
    headers = {
        'Authorization': f'Bearer {read_token(token_file)}',
        'Content-Type': 'application/json'
    }

    # Fetch Jira data
    data = get_jira_data(ticket_id, jira_server, headers)
    if not data:
        return

    summary = data['fields']['summary'].lower()
    user_name = extract_user_name(data['fields']['summary'])

    # Split the user's name into last and first name
    try:
        last_name, first_name = user_name.split(", ")
    except ValueError:
        print(f"User name format is incorrect for {user_name}")
        return

    # Search for the incident number in the CSV
    incident_number = search_incident_csv("inputs/incident.csv", last_name, first_name)

    # Determine the template
    template = determine_template(summary)
    print("summary: ", summary)
    if not template:
        return

    # Process subtasks
    granted_roles, pending_roles, denied_roles = process_subtasks(data['fields']['subtasks'], jira_server, headers, user_name)

    # Construct sections only if there are roles
    granted_section = f"\n        You have been granted the following roles:\n        • " + "\n        • ".join(granted_roles) + "\n" if granted_roles else ""
    pending_section = f"\n        We are waiting for approval for:\n        • " + "\n        • ".join(pending_roles) + "\n" if pending_roles else ""
    denied_section = f"\n        The following roles were denied:\n        • " + "\n        • ".join(denied_roles) + "\n" if denied_roles else ""

    # Fill in the template
    email_message = template.format(
        granted_section=granted_section,
        pending_section=pending_section,
        denied_section=denied_section
    )

    # Save the email message
    save_email_message(user_name, output_folder, email_message, ticket_id, incident_number)

