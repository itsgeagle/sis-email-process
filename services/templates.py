"""Email template strings for SIS access notifications.

These templates match the exact format of the original generate_template.py output.
The leading newline and trailing newline are intentional to match the old script.
"""

NEW_ACCESS_TEMPLATE = """
Hello,

You now have been granted access to UC Berkeley's Student Information Systems. This access is based on a request submitted to the Campus Applications & Data (CAD) security team. Please note that your access is based on your position and duties at UC Berkeley and is subject to periodic review.

An employee event or change in job duties will trigger a review and potential loss of some or all currently assigned roles/access. In order to regain access to roles or access thereafter, you will need to complete a new Access Request form.

{granted_section}{pending_section}{denied_section}

Please select SIS Campus Solutions or paste the following URL into your address bar:
https://bcsint.is.berkeley.edu

In the event of any login issues:

\u2022 Please clear your browser cache before logging in to SIS Campus Solutions by following these instructions: https://www.wikihow.com/Clear-Your-Browser%27s-Cache
\u2022 Logging directly into Campus Solutions now requires the use of a Virtual Private Network (VPN). Please see the following pages for more information:
- https://security.berkeley.edu/services/bsecure/bsecure-remote-access-vpn
- https://calnetweb.berkeley.edu/calnet-technologists/duo-mfa-service-non-web-integrations

Note:
If you have difficulty accessing SIS or have questions about your access, do not reply to this email as it is not monitored. Please reply to the ServiceNow ticket being created for this request.

Please contact Student Information Systems by replying to the ServiceNow ticket created for this request.

Thanks,
CAD Security Team
"""

MODIFY_ACCESS_TEMPLATE = """
Hello,

Your SIS account has been updated; added to your existing roles are the requested role(s) below:

{granted_section}{pending_section}{denied_section}

An employee event or change in job duties will trigger a review and potential loss of some or all currently assigned roles/access. In order to regain access to roles or access thereafter, you will need to complete a new Access Request form.

Please select SIS Campus Solutions or paste the following URL into your address bar:
https://bcsint.is.berkeley.edu

In the event of any login issues:

\u2022 Please clear your browser cache before logging in to SIS Campus Solutions by following these instructions: https://www.wikihow.com/Clear-Your-Browser%27s-Cache
\u2022 Logging directly into Campus Solutions now requires the use of a Virtual Private Network (VPN). Please see the following pages for more information:
- https://security.berkeley.edu/services/bsecure/bsecure-remote-access-vpn
- https://calnetweb.berkeley.edu/calnet-technologists/duo-mfa-service-non-web-integrations

Note:
If you have difficulty accessing SIS or have questions about your access, do not reply to this email as it is not monitored. Please reply to the ServiceNow ticket being created for this request.

Please contact Student Information Systems by replying to the ServiceNow ticket created for this request.

Thanks,
CAD Security Team
"""
