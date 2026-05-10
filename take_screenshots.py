import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def take_screenshots():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--hide-scrollbars')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--log-level=3')

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"Error setting up Selenium: {e}")
        return

    print("Navigating to RouteCraft...")
    driver.get("http://127.0.0.1:5000")
    time.sleep(3)  # Wait for map to load

    # 1. Screenshot of the empty state/home page
    home_path = os.path.join(out_dir, "routecraft_home.jpg")
    # Save as png first, then we can convert or just keep png. The user wanted pictures.
    driver.save_screenshot(home_path)
    print(f"Saved {home_path}")

    print("Searching for routes from Koramangala to Whitefield...")
    # Fill in the form
    source_input = driver.find_element(By.ID, "source")
    source_input.clear()
    source_input.send_keys("Koramangala")

    dest_input = driver.find_element(By.ID, "destination")
    dest_input.clear()
    dest_input.send_keys("Whitefield")

    # Click find routes
    find_btn = driver.find_element(By.ID, "findRouteBtn")
    find_btn.click()

    # Wait for ML inference and routing (can take ~15-20s if cold cache)
    print("Waiting for route calculation...")
    time.sleep(25)

    # 2. Screenshot of the results
    results_path = os.path.join(out_dir, "routecraft_results.jpg")
    driver.save_screenshot(results_path)
    print(f"Saved {results_path}")

    driver.quit()
    print("Screenshots captured successfully.")

if __name__ == "__main__":
    take_screenshots()
