"""Selenium-based ServiceNow automation for incident resolution.

Targets the Next Experience UI (Polaris) used by berkeley.service-now.com.
URLs follow the /now/nav/ui/ pattern. Most elements are inside shadow DOM
or web components, so we use a mix of CSS selectors and JavaScript execution.
"""

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
WAIT_TIMEOUT = 30
# Short pause for UI animations/transitions
UI_PAUSE = 2


class SnowAutomationError(Exception):
    """Raised when a ServiceNow automation step fails."""


class SnowAutomation:
    """Automate ServiceNow incident operations via Chrome browser.

    Targets the Next Experience (Polaris) UI. The browser session stays
    open between operations so CalNet SSO login only needs to happen once.
    """

    def __init__(self, instance_url: str):
        self.instance_url = instance_url.rstrip("/")
        self.driver = None

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

    def start_session(self):
        """Open ServiceNow and let the user complete SSO login.

        Detects login completion by waiting for the URL to contain '/now/'
        (the Next Experience landing page), since shadow DOM prevents
        reliable element-based detection.
        """
        self._ensure_driver()
        self.driver.get(self.instance_url)
        logger.info("Navigated to %s — complete SSO login if prompted", self.instance_url)

        # Wait for URL to land on the Next Experience home page.
        # After CalNet SSO + Duo, the browser redirects to something like:
        #   https://berkeley.service-now.com/now/nav/ui/home
        try:
            WebDriverWait(self.driver, 180).until(
                lambda d: "/now/" in d.current_url
                or "navpage.do" in d.current_url
                or "home" in d.current_url
            )
            logger.info("SSO login complete (URL: %s)", self.driver.current_url)
        except TimeoutException:
            logger.warning("Could not auto-detect login completion.")
            input("Press Enter after you have logged in to ServiceNow...")

    def find_incident_by_search(self, search_query: str) -> list[dict]:
        """Search ServiceNow for incidents matching a query string.

        Uses the incident list URL with a sysparm_query filter, which works
        in both classic and Next Experience (SNOW redirects appropriately).

        Args:
            search_query: Text to search for in short_description (typically user name).

        Returns:
            List of dicts with 'number' and 'short_description'.
        """
        self._ensure_driver()

        # Use the classic list URL — SNOW Next Experience will render it
        # within its workspace. This is more reliable than trying to
        # interact with the Polaris search components.
        encoded_query = urllib.parse.quote(
            f"short_descriptionLIKE{search_query}^active=true",
            safe="=^",
        )
        list_url = (
            f"{self.instance_url}/now/nav/ui/classic/params/target/incident_list.do"
            f"%3Fsysparm_query%3D{urllib.parse.quote(f'short_descriptionLIKE{search_query}^active=true', safe='')}"
        )
        self.driver.get(list_url)
        time.sleep(UI_PAUSE * 3)  # Next Experience takes time to load embedded classic frames

        incidents = self._scrape_incident_list()

        if not incidents:
            # Fallback: try direct classic URL
            classic_url = (
                f"{self.instance_url}/incident_list.do"
                f"?sysparm_query=short_descriptionLIKE{urllib.parse.quote(search_query)}^active=true"
            )
            self.driver.get(classic_url)
            time.sleep(UI_PAUSE * 3)
            incidents = self._scrape_incident_list()

        logger.info("Found %d incidents matching '%s'", len(incidents), search_query)
        return incidents

    def _scrape_incident_list(self) -> list[dict]:
        """Scrape incident numbers and descriptions from the current page.

        Handles both Next Experience embedded frames and classic list views.
        """
        incidents = []

        # Try to find an iframe (classic content embedded in Next Experience)
        original_frame = None
        try:
            iframe = self._wait_for(By.CSS_SELECTOR, "iframe[name='gsft_main'], iframe.embed", timeout=8)
            self.driver.switch_to.frame(iframe)
            original_frame = True
        except TimeoutException:
            pass  # Not in a framed layout, or pure Next Experience

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

            # Strategy 2: If no classic rows, look for Next Experience list items
            if not incidents:
                # Next Experience renders lists as <now-record-list> or similar
                # Try extracting via links that contain INC numbers
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

            # Strategy 3: Just find any text that looks like an incident number
            if not incidents:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                import re
                inc_numbers = re.findall(r"(INC\d{7,})", page_text)
                for num in dict.fromkeys(inc_numbers):  # deduplicate, preserve order
                    incidents.append({"number": num, "short_description": ""})

        except Exception as e:
            logger.warning("Error scraping incident list: %s", e)
        finally:
            if original_frame:
                self.driver.switch_to.default_content()

        return incidents

    def _parse_classic_row(self, row) -> dict | None:
        """Parse an incident number and description from a classic list table row."""
        try:
            # Look for a link with the incident number
            links = row.find_elements(By.TAG_NAME, "a")
            number = ""
            for link in links:
                text = link.text.strip()
                if text.startswith("INC"):
                    number = text
                    break

            if not number:
                # Try all cells
                cells = row.find_elements(By.TAG_NAME, "td")
                for cell in cells:
                    text = cell.text.strip()
                    if text.startswith("INC"):
                        number = text
                        break

            if not number:
                return None

            # Get short description — usually in a cell with more text
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
        """Navigate directly to a specific incident by number."""
        self._ensure_driver()
        # Use the classic URL pattern — works in both classic and Next Experience
        url = (
            f"{self.instance_url}/now/nav/ui/classic/params/target/"
            f"incident.do%3Fsysparm_query%3Dnumber%3D{incident_number}"
        )
        self.driver.get(url)
        time.sleep(UI_PAUSE * 3)

        # Switch to iframe if present (classic form embedded in Next Experience)
        try:
            iframe = self._wait_for(By.CSS_SELECTOR, "iframe[name='gsft_main'], iframe.embed", timeout=10)
            self.driver.switch_to.frame(iframe)
        except TimeoutException:
            pass

        logger.info("Opened incident %s", incident_number)

    def post_work_note(self, text: str):
        """Add a work note to the currently open incident."""
        try:
            # In classic form (possibly inside iframe), find work notes
            # First try clicking the "Work notes" tab/label to switch to it
            tab_selectors = [
                (By.CSS_SELECTOR, "span.tab_caption_text[title='Work notes']"),
                (By.CSS_SELECTOR, "label[for*='work_notes']"),
                (By.CSS_SELECTOR, "#work_notes_label"),
                (By.XPATH, "//span[contains(text(), 'Work notes')]"),
                (By.XPATH, "//a[contains(text(), 'Work Notes')]"),
            ]
            for by, selector in tab_selectors:
                try:
                    tab = self._wait_for(by, selector, timeout=3, clickable=True)
                    tab.click()
                    time.sleep(UI_PAUSE)
                    break
                except TimeoutException:
                    continue

            # Now find the textarea
            textarea_selectors = [
                (By.ID, "activity-stream-work_notes-textarea"),
                (By.CSS_SELECTOR, "textarea[id*='work_notes']"),
                (By.CSS_SELECTOR, "textarea[name='work_notes']"),
                (By.ID, "incident.work_notes"),
            ]

            textarea = None
            for by, selector in textarea_selectors:
                try:
                    textarea = self._wait_for(by, selector, timeout=5)
                    break
                except TimeoutException:
                    continue

            if textarea is None:
                raise SnowAutomationError(
                    "Could not find the work notes textarea. "
                    "Please add the work note manually in the browser."
                )

            textarea.click()
            time.sleep(UI_PAUSE / 2)
            textarea.clear()
            textarea.send_keys(text)
            logger.info("Work note text entered")

        except SnowAutomationError:
            raise
        except Exception as e:
            raise SnowAutomationError(f"Failed to post work note: {e}")

    def resolve_incident(self):
        """Fill resolution fields and save the incident.

        Sets: category=Service Request, impact=Individual, urgency=Low,
        state=Resolved, close_code=Solved, close_notes=Security access updated.
        """
        try:
            field_updates = [
                ("incident.category", "Service Request"),
                ("incident.impact", "3"),       # 3 = Individual/Low
                ("incident.urgency", "3"),       # 3 = Low
                ("incident.state", "6"),         # 6 = Resolved
                ("incident.close_code", "Solved (Permanently)"),
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
        # ServiceNow classic forms respond best to JavaScript-driven changes
        # because they use onChange handlers tied to GlideForm
        try:
            # First try GlideForm API (most reliable in classic forms)
            # g_form.setValue() triggers all the right server-side logic
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
        # Try GlideForm first
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
