import warnings
warnings.warn(
    "This script is deprecated. Use 'python app.py' for auto-scanning via Jira filter.",
    DeprecationWarning,
    stacklevel=1,
)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

# Read the token from the inputs folder
def read_token():
    token_path = "inputs/token.txt"
    try:
        with open(token_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"Token file not found at {token_path}")
        return None

def login_and_export_jira():
    # Load the token
    token = read_token()
    if not token:
        print("Jira token is missing. Exiting...")
        return

    # Set up WebDriver
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')
    prefs = {
        "download.default_directory": os.path.abspath("downloads"),  # Ensure this folder exists
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)

    try:
        # Navigate to Jira using token-based authentication
        jira_url = f"https://{token}:x-token-auth@jira-secure.berkeley.edu/issues/?filter=32386"
        driver.get(jira_url)

        # Wait for the page to load and ensure we are logged in
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "export-csv"))  # Replace with actual export button ID or selector
        )
        print("Login successful!")

        # Find and click the Export CSV button
        export_button = driver.find_element(By.ID, "export-csv")  # Replace with correct selector
        export_button.click()

        # Wait for the download to complete
        time.sleep(30)  # Adjust based on the file size and download speed

        print("CSV export successful! Check the downloads folder.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

# Run the script
if __name__ == "__main__":
    login_and_export_jira()
