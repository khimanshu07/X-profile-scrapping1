import csv
import time
import re
import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Twitter login credentials - replace with your own
TWITTER_ID = ""  # Enter your Twitter username
TWITTER_PASSWORD = ""  # Enter your password

# MySQL database configuration
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "Enter_your_username",  # Replace with your MySQL username
    "password": "Enter_your_password",  # Replace with your MySQL password
    "database": "twitter_data",
}

def setup_driver():
    """Set up and return a configured Chrome webdriver"""
    options = Options()
    # options.add_argument("--headless")  # Uncomment to run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36")
    options.add_argument("--window-size=1920,1080")
    
    # Set up the driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def login_to_twitter(driver):
    """Login to Twitter account using mobile number"""
    try:
        # Open Twitter login page
        driver.get("https://twitter.com/i/flow/login")
        
        # Wait for the login page to load
        wait = WebDriverWait(driver, 15)
        
        # Enter phone number
        print("Attempting to login to Twitter...")
        login_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@autocomplete='username']")))
        login_field.send_keys(TWITTER_ID)
        login_field.send_keys(Keys.RETURN)
        
        # Wait for the password field
        time.sleep(2)
        
        # Try different selectors for password field as Twitter might change them
        password_selectors = [
            "//input[@name='password']",
            "//input[@autocomplete='current-password']",
            "//div[@data-testid='Password']//input"
        ]
        
        password_field = None
        for selector in password_selectors:
            try:
                password_field = wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                break
            except:
                continue
        
        if not password_field:
            print("Couldn't find password field")
            return False
            
        password_field.send_keys(TWITTER_PASSWORD)
        password_field.send_keys(Keys.RETURN)
        
        # Wait for login to complete
        time.sleep(5)
        
        # Check if login was successful by looking for home timeline
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']")))
            print("Successfully logged in to Twitter")
            return True
        except:
            print("Login unsuccessful. Check your credentials or Twitter might be requiring additional verification.")
            return False
            
    except Exception as e:
        print(f"Error during login: {str(e)}")
        return False

def format_count(count_text):
    """Convert Twitter number format to integer string"""
    if not count_text:
        return "N/A"
    
    # Remove commas and any non-numeric characters except digits, dots, K, M
    count_text = re.sub(r'[^\d\.KkMm]', '', count_text)
    
    if not count_text:
        return "N/A"
    
    # Convert K, M to actual numbers
    if 'K' in count_text.upper():
        count_text = str(int(float(count_text.upper().replace('K', '')) * 1000))
    elif 'M' in count_text.upper():
        count_text = str(int(float(count_text.upper().replace('M', '')) * 1000000))
    
    return count_text

def extract_count_from_text(element_text):
    """Extract just the number from text like '123 Following' or 'Following 123'"""
    # Find all numbers in the text (including those with K or M suffix)
    numbers = re.findall(r'\b\d+[,\.]?\d*[KkMm]?\b', element_text)
    if numbers:
        return numbers[0]  # Return the first number found
    return ""

def normalize_twitter_url(url):
    """Normalize Twitter URLs to a standard format and handle @ symbols"""
    # Handle URLs that include the @ symbol
    if '@' in url:
        # Remove the @ symbol from the username part
        parts = url.split('.com/')
        if len(parts) > 1:
            username_part = parts[1]
            if username_part.startswith('@'):
                username_part = username_part[1:]
            url = parts[0] + '.com/' + username_part
    
    # Ensure URL has the correct protocol
    if not (url.startswith('http://') or url.startswith('https://')):
        url = 'https://' + url
    
    return url

def is_valid_twitter_url(url):
    """Check if the URL is a valid Twitter profile URL"""
    # First normalize the URL
    url = normalize_twitter_url(url)
    
    # Basic pattern for Twitter URLs
    twitter_pattern = re.compile(r'https?://(www\.)?(twitter|x)\.com/[a-zA-Z0-9_]+')
    return bool(twitter_pattern.match(url))

def check_profile_exists(driver, url):
    """Check if the Twitter profile exists by looking for specific error indicators"""
    try:
        # Look for elements that indicate a profile doesn't exist
        error_elements = driver.find_elements(By.XPATH, "//div[contains(text(), 'This account doesn')]")
        
        # Check for other error messages
        for error_text in ["doesn't exist", "Account suspended", "Page not found"]:
            if error_text in driver.page_source:
                return False
                
        # Additional check for the primary column (should exist for valid profiles)
        primary_column = driver.find_elements(By.XPATH, "//div[@data-testid='primaryColumn']")
        if not primary_column:
            return False
            
        return True
    except Exception as e:
        print(f"Error checking if profile exists: {str(e)}")
        return False

def scrape_twitter_profile(driver, profile_url):
    """Scrape data from a Twitter profile page"""
    # Normalize the URL
    normalized_url = normalize_twitter_url(profile_url)
    
    profile_data = {
        'profile_url': profile_url,
        'bio': "N/A",
        'following_count': "N/A",
        'followers_count': "N/A",
        'location': "N/A",
        'website': "N/A",
        'status': "Success"
    }
    
    try:
        # Validate URL format first
        if not is_valid_twitter_url(profile_url):
            profile_data['status'] = "Invalid URL format"
            print(f"Invalid Twitter URL format: {profile_url}")
            return profile_data
        
        # Load the Twitter profile page with the normalized URL
        driver.get(normalized_url)
        
        # Wait for the page to load (wait for primary column)
        wait = WebDriverWait(driver, 15)
        
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']")))
        except TimeoutException:
            profile_data['status'] = "Profile not found or page failed to load"
            print(f"Profile not found or failed to load: {normalized_url}")
            return profile_data
        
        # Check if profile exists
        if not check_profile_exists(driver, normalized_url):
            profile_data['status'] = "Profile doesn't exist"
            print(f"Profile doesn't exist: {normalized_url}")
            return profile_data
        
        # Give the page more time to fully render
        time.sleep(5)
        
        # Extract bio
        try:
            bio = driver.find_element(By.XPATH, "//div[@data-testid='UserDescription']").text
            profile_data['bio'] = bio
        except:
            pass
        
        # Extract following count
        try:
            following_count = driver.find_element(By.XPATH, "//a[contains(@href, '/following')]//span").text
            following_count = extract_count_from_text(following_count)
            profile_data['following_count'] = format_count(following_count)
        except:
            pass
        
        # Extract followers count
        try:
            followers_count = driver.find_element(By.XPATH, "//a[contains(@href, '/verified_followers')]//span").text
            followers_count = extract_count_from_text(followers_count)
            profile_data['followers_count'] = format_count(followers_count)
        except:
            pass
        
        # Extract location
        try:
            location = driver.find_element(By.XPATH, "//span[@data-testid='UserLocation']").text
            profile_data['location'] = location
        except:
            pass
        
        # Extract website
        try:
            website = driver.find_element(By.XPATH, "//a[@data-testid='UserUrl']").text
            profile_data['website'] = website
        except:
            pass
        
    except Exception as e:
        profile_data['status'] = f"Error: {str(e)}"
    
    return profile_data

def insert_into_mysql(data):
    """Insert scraped data into MySQL database"""
    try:
        # Connect to MySQL database
        connection = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = connection.cursor()

        # Insert query
        query = """
        INSERT INTO profiles (profile_url, bio, following_count, followers_count, location, website, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            data["profile_url"],
            data["bio"],
            data["following_count"],
            data["followers_count"],
            data["location"],
            data["website"],
            data["status"],
        )

        # Execute the query
        cursor.execute(query, values)
        connection.commit()
        cursor.close()
        connection.close()
        print(f"Data inserted for {data['profile_url']}")
    except mysql.connector.Error as err:
        print(f"Error inserting data into MySQL: {err}")

def main():
    # Initialize the webdriver
    driver = setup_driver()
    
    try:
        # Login to Twitter
        if not login_to_twitter(driver):
            print("Failed to login. Exiting.")
            return
        
        # Read Twitter profile URLs from the input CSV file
        input_profiles = []
        try:
            with open('twitter_links.csv', 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    if row and row[0].strip():  # Check if the row is not empty
                        url = row[0].strip()
                        input_profiles.append(url)
        except Exception as e:
            print(f"Error reading input file: {str(e)}")
            return
        
        if not input_profiles:
            print("No valid Twitter profile URLs found in the input file.")
            return
        
        # Scrape data for each profile and insert into MySQL
        for profile_url in input_profiles:
            print(f"Scraping: {profile_url}")
            profile_data = scrape_twitter_profile(driver, profile_url)
            # Insert data into MySQL
            insert_into_mysql(profile_data)
            # Add a delay between requests to avoid rate limiting
            time.sleep(3)
        
        print("Scraping and data insertion completed.")
    
    finally:
        # Clean up
        driver.quit()

if __name__ == "__main__":
    main()