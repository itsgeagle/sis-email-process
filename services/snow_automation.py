"""Selenium-based ServiceNow automation for incident resolution.

Uses classic ServiceNow URLs (incident.do, incident_list.do) to avoid
the Next Experience (Polaris) shadow DOM that hides elements from Selenium.
"""

from __future__ import annotations

import logging
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

# Timeout for element waits (seconds)
WAIT_TIMEOUT = 15
# Short pause for UI animations/transitions
UI_PAUSE = 1


class SnowAutomationError(Exception):
    """Raised when a ServiceNow automation step fails."""


class SnowAutomation:
    """Automate ServiceNow incident operations via Chrome browser.

    Uses classic ServiceNow URLs so all form elements are directly
    accessible to Selenium (no shadow DOM). The browser session stays
    open between operations so CalNet SSO login only needs to happen once.
    """

    def __init__(self, instance_url: str):
        self.instance_url = instance_url.rstrip("/")
        self.driver = None
        self._in_iframe = False

    def _ensure_driver(self):
        """Start Chrome if not already running."""
        if self.driver is None:
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            self.driver = webdriver.Chrome(options=options)
            logger.info("Chrome browser started")

    def _wait_for(self, by, value, timeout=WAIT_TIMEOUT, clickable=False):
        """Wait for an element and return it."""
        condition = (
            EC.element_to_be_clickable((by, value))
            if clickable
            else EC.presence_of_element_located((by, value))
        )
        return WebDriverWait(self.driver, timeout).until(condition)

    def _wait_for_page_ready(self, timeout=WAIT_TIMEOUT):
        """Wait for the page to finish loading instead of using fixed sleeps."""
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # Brief pause for dynamic rendering after DOM ready
        time.sleep(UI_PAUSE)

    def _switch_to_iframe_if_present(self, timeout=5):
        """Switch into gsft_main iframe if present, updating _in_iframe flag."""
        self._in_iframe = False
        try:
            iframe = self._wait_for(
                By.CSS_SELECTOR, "iframe[name='gsft_main'], iframe.embed", timeout=timeout
            )
            self.driver.switch_to.frame(iframe)
            self._in_iframe = True
        except TimeoutException:
            pass

    def start_session(self):
        """Open ServiceNow and let the user complete SSO login.

        Navigates to the instance URL and waits for the browser to land
        on a post-login page.
        """
        self._ensure_driver()
        self.driver.get(self.instance_url)
        logger.info("Navigated to %s — complete SSO login if prompted", self.instance_url)

        try:
            WebDriverWait(self.driver, 180).until(
                lambda d: "/now/" in d.current_url
                or "navpage.do" in d.current_url
                or "home" in d.current_url
                or "incident.do" in d.current_url
                or "nav_to.do" in d.current_url
                or "welcome.do" in d.current_url
            )
            logger.info("SSO login complete (URL: %s)", self.driver.current_url)
        except TimeoutException:
            logger.warning("Could not auto-detect login completion.")
            input("Press Enter after you have logged in to ServiceNow...")

    def find_incident_by_search(self, search_query: str) -> list[dict]:
        """Search ServiceNow for incidents matching a query string.

        Uses the classic incident_list.do URL directly to avoid shadow DOM.

        Args:
            search_query: Text to search for in short_description (typically user name).

        Returns:
            List of dicts with 'number' and 'short_description'.
        """
        self._ensure_driver()

        list_url = (
            f"{self.instance_url}/incident_list.do"
            f"?sysparm_query=short_descriptionLIKE{urllib.parse.quote(search_query)}^active=true"
        )
        self.driver.get(list_url)
        self._wait_for_page_ready()

        incidents = self._scrape_incident_list()
        logger.info("Found %d incidents matching '%s'", len(incidents), search_query)
        return incidents

    def _scrape_incident_list(self) -> list[dict]:
        """Scrape incident numbers and descriptions from the current page."""
        incidents = []

        # Classic URL may still render inside an iframe in some configs
        self._switch_to_iframe_if_present(timeout=3)

        try:
            # Strategy 1: Classic list table rows
            rows = self.driver.find_elements(
                By.CSS_SELECTOR,
                "tr.list_row, tr.list_odd, tr.list_even, tr[class*='list_row']"
            )
            for row in rows:
                inc = self._parse_classic_row(row)
                if inc:
                    incidents.append(inc)

            # Strategy 2: Links containing INC numbers
            if not incidents:
                links = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "a[href*='incident.do'], a[aria-label*='INC'], [data-short-description]"
                )
                for link in links:
                    text = link.text.strip()
                    if text.startswith("INC"):
                        incidents.append({
                            "number": text,
                            "short_description": link.get_attribute("aria-label") or "",
                        })

            # Strategy 3: Regex scan of page text
            if not incidents:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                import re
                inc_numbers = re.findall(r"(INC\d{7,})", page_text)
                for num in dict.fromkeys(inc_numbers):  # deduplicate, preserve order
                    incidents.append({"number": num, "short_description": ""})

        except Exception as e:
            logger.warning("Error scraping incident list: %s", e)
        finally:
            if self._in_iframe:
                self.driver.switch_to.default_content()
                self._in_iframe = False

        return incidents

    def _parse_classic_row(self, row) -> dict | None:
        """Parse an incident number and description from a classic list table row."""
        try:
            links = row.find_elements(By.TAG_NAME, "a")
            number = ""
            for link in links:
                text = link.text.strip()
                if text.startswith("INC"):
                    number = text
                    break

            if not number:
                cells = row.find_elements(By.TAG_NAME, "td")
                for cell in cells:
                    text = cell.text.strip()
                    if text.startswith("INC"):
                        number = text
                        break

            if not number:
                return None

            short_desc = ""
            cells = row.find_elements(By.TAG_NAME, "td")
            for cell in cells:
                text = cell.text.strip()
                if text and not text.startswith("INC") and len(text) > 10:
                    short_desc = text
                    break

            return {"number": number, "short_description": short_desc}
        except Exception:
            return None

    def open_incident(self, incident_number: str):
        """Navigate directly to a specific incident using the classic URL."""
        self._ensure_driver()
        url = (
            f"{self.instance_url}/incident.do"
            f"?sysparm_query=number={incident_number}"
        )
        self.driver.get(url)
        self._wait_for_page_ready()
        self._switch_to_iframe_if_present(timeout=5)
        logger.info("Opened incident %s", incident_number)

    def _find_textarea(self):
        """Search for the activity stream textarea in all frame contexts.

        Returns the textarea element, or None. Leaves the driver in
        whichever frame context the textarea was found in.
        """
        selectors = [
            (By.ID, "activity-stream-textarea"),
            (By.CSS_SELECTOR, "textarea[data-stream-text-input]"),
            (By.CSS_SELECTOR, "textarea.sn-string-textarea"),
        ]

        # Try current context first
        for by, selector in selectors:
            try:
                return self._wait_for(by, selector, timeout=3)
            except TimeoutException:
                continue

        # Try the other context (if in iframe → outer, if outer → iframe)
        if self._in_iframe:
            self.driver.switch_to.default_content()
        else:
            try:
                iframe = self._wait_for(
                    By.CSS_SELECTOR, "iframe[name='gsft_main'], iframe.embed", timeout=3
                )
                self.driver.switch_to.frame(iframe)
            except TimeoutException:
                return None

        for by, selector in selectors:
            try:
                return self._wait_for(by, selector, timeout=3)
            except TimeoutException:
                continue

        return None

    def post_comment(self, text: str):
        """Add an additional comment (customer visible) to the currently open incident.

        The activity stream textarea (id="activity-stream-textarea") defaults to
        "Additional comments" mode, so we just need to find it and type.
        """
        try:
            textarea = self._find_textarea()

            if textarea is None:
                raise SnowAutomationError(
                    "Could not find the activity stream textarea. "
                    "Please add the comment manually in the browser."
                )

            # Ensure we're on "Additional comments" (not "Work notes").
            current_type = textarea.get_attribute("data-stream-text-input")
            if current_type and current_type != "comments":
                comments_toggle_selectors = [
                    (By.CSS_SELECTOR, "[data-stream-text-input='comments']"),
                    (By.XPATH, "//a[contains(text(), 'Additional comments')]"),
                    (By.XPATH, "//span[contains(text(), 'Additional comments')]"),
                ]
                for by, selector in comments_toggle_selectors:
                    try:
                        toggle = self._wait_for(by, selector, timeout=2, clickable=True)
                        toggle.click()
                        time.sleep(UI_PAUSE)
                        break
                    except TimeoutException:
                        continue

            textarea.click()
            time.sleep(UI_PAUSE / 2)
            textarea.clear()
            textarea.send_keys(text)
            logger.info("Additional comment text entered")

            # Click the Post button to submit the comment
            post_selectors = [
                (By.CSS_SELECTOR, "button.activity-submit"),
                (By.CSS_SELECTOR, "button[id*='post']"),
                (By.XPATH, "//button[contains(text(), 'Post')]"),
                (By.CSS_SELECTOR, "input[value='Post']"),
            ]
            for by, selector in post_selectors:
                try:
                    post_btn = self._wait_for(by, selector, timeout=3, clickable=True)
                    post_btn.click()
                    time.sleep(UI_PAUSE)
                    logger.info("Comment posted")
                    break
                except TimeoutException:
                    continue
            else:
                logger.warning("Could not find Post button — comment was typed but may need manual posting")

        except SnowAutomationError:
            raise
        except Exception as e:
            raise SnowAutomationError(f"Failed to post comment: {e}")

    def resolve_incident(self):
        """Fill resolution fields and save the incident.

        Sets: category=Service Request, impact=Individual, urgency=Low,
        state=Resolved, close_code=Solved, close_notes=Security access updated.
        """
        try:
            # Ensure we're in the right frame context for g_form access.
            self.driver.switch_to.default_content()
            self._switch_to_iframe_if_present(timeout=5)

            # Assign to current logged-in user
            try:
                self.driver.execute_script("""
                    if (typeof g_form !== 'undefined' && typeof g_user !== 'undefined') {
                        g_form.setValue('assigned_to', g_user.userID);
                    }
                """)
                time.sleep(UI_PAUSE / 2)
                logger.debug("Set assigned_to to current user")
            except Exception as e:
                logger.warning("Could not set assigned_to: %s", e)

            field_updates = [
                ("incident.category", "Service Request"),
                ("incident.impact", "4"),       # 4 = Individual
                ("incident.urgency", "3"),       # 3 = Low
                ("incident.state", "6"),         # 6 = Resolved
                ("incident.close_code", "Solved"),
            ]

            for field_id, value in field_updates:
                self._set_field(field_id, value)

            # Set close notes
            self._set_text_field("incident.close_notes", "Security access updated.")

            # Click Save/Update
            save_selectors = [
                (By.ID, "sysverb_update"),
                (By.CSS_SELECTOR, "button#sysverb_update"),
                (By.XPATH, "//button[@id='sysverb_update']"),
                (By.XPATH, "//button[contains(text(), 'Update')]"),
                (By.XPATH, "//button[contains(text(), 'Save')]"),
            ]
            for by, selector in save_selectors:
                try:
                    btn = self._wait_for(by, selector, timeout=5, clickable=True)
                    btn.click()
                    time.sleep(UI_PAUSE * 2)
                    logger.info("Incident resolved and saved")
                    self.driver.switch_to.default_content()
                    return
                except TimeoutException:
                    continue

            self.driver.switch_to.default_content()
            logger.warning(
                "Could not find Save/Update button — fields were set but may need manual save"
            )

        except SnowAutomationError:
            self.driver.switch_to.default_content()
            raise
        except Exception as e:
            self.driver.switch_to.default_content()
            raise SnowAutomationError(f"Failed to resolve incident: {e}")

    def _set_field(self, field_id: str, value: str):
        """Set a select/dropdown field by its ID using JavaScript for reliability."""
        try:
            field_name = field_id.replace("incident.", "")
            result = self.driver.execute_script(
                f"""
                if (typeof g_form !== 'undefined') {{
                    g_form.setValue('{field_name}', '{value}');
                    return true;
                }}
                return false;
                """
            )
            if result:
                time.sleep(UI_PAUSE / 2)
                logger.debug("Set %s = %s via g_form", field_id, value)
                return
        except Exception:
            pass

        # Fallback: try as a Select element
        try:
            from selenium.webdriver.support.ui import Select
            element = self._wait_for(By.ID, field_id, timeout=5)
            select = Select(element)
            try:
                select.select_by_visible_text(value)
            except Exception:
                select.select_by_value(value)
            time.sleep(UI_PAUSE / 2)
            logger.debug("Set %s = %s via Select", field_id, value)
        except Exception:
            # Last resort: input field
            try:
                element = self._wait_for(By.ID, field_id, timeout=3)
                element.clear()
                element.send_keys(value)
                time.sleep(UI_PAUSE / 2)
            except Exception as e:
                logger.warning("Could not set field %s: %s", field_id, e)

    def _set_text_field(self, field_id: str, value: str):
        """Set a text/textarea field."""
        field_name = field_id.replace("incident.", "")
        try:
            result = self.driver.execute_script(
                f"""
                if (typeof g_form !== 'undefined') {{
                    g_form.setValue('{field_name}', '{value}');
                    return true;
                }}
                return false;
                """
            )
            if result:
                time.sleep(UI_PAUSE / 2)
                logger.debug("Set text field %s via g_form", field_id)
                return
        except Exception:
            pass

        # Fallback
        try:
            element = self._wait_for(By.ID, field_id, timeout=5)
            element.clear()
            element.send_keys(value)
            time.sleep(UI_PAUSE / 2)
            logger.debug("Set text field %s directly", field_id)
        except TimeoutException:
            logger.warning("Could not find text field %s", field_id)

    def close(self):
        """Quit the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Browser closed")
