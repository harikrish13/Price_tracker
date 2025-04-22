from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
import re
import time
import os
import sys
import shutil
import logging
import random
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from models import get_db, PriceAlert
from email_utils import send_price_alert

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProductResult(BaseModel):
    title: str
    price: float
    url: str
    source: str
    image_url: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None

class AlertCreate(BaseModel):
    user_email: str
    product_url: str
    product_title: str
    target_price: float

class AlertResponse(BaseModel):
    id: int
    user_email: str
    product_url: str
    product_title: str
    target_price: float
    current_price: float
    is_active: bool
    created_at: datetime
    last_checked: datetime

def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
    ]
    return random.choice(user_agents)

def setup_driver():
    try:
        logger.info("Setting up undetected-chromedriver...")
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={get_random_user_agent()}")
        
        # Additional options to avoid detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        
        driver = uc.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("Successfully created driver with undetected-chromedriver")
        return driver
    except Exception as e:
        logger.error(f"Error setting up ChromeDriver: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize browser: {str(e)}")

def extract_price(price_text: str) -> float:
    if not price_text:
        return 0.0
    try:
        # Remove any currency symbols and commas
        cleaned_text = price_text.replace('$', '').replace(',', '').strip()
        # Find the first number in the text
        price_match = re.search(r'\d+\.?\d*', cleaned_text)
        return float(price_match.group()) if price_match else 0.0
    except Exception as e:
        logger.error(f"Error extracting price from {price_text}: {str(e)}")
        return 0.0

def safe_get_text(element, selector: str, default: str = "") -> str:
    try:
        return element.find_element(By.CSS_SELECTOR, selector).text
    except Exception:
        return default

def safe_get_attribute(element, selector: str, attribute: str, default: str = "") -> str:
    try:
        return element.find_element(By.CSS_SELECTOR, selector).get_attribute(attribute)
    except Exception:
        return default

def scrape_amazon(driver: webdriver.Chrome, query: str) -> List[ProductResult]:
    results = []
    try:
        url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}"
        logger.info(f"Scraping Amazon: {url}")
        
        # Add random delay before request
        time.sleep(random.uniform(2, 4))
        driver.get(url)
        
        # Wait for main content to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot"))
        )
        
        # Multiple selectors for product containers
        selectors = [
            "div.s-result-item[data-component-type='s-search-result']",
            "div.sg-col-4-of-12",
            "div.sg-col-4-of-16"
        ]
        
        products = []
        for selector in selectors:
            products = driver.find_elements(By.CSS_SELECTOR, selector)
            if products:
                logger.info(f"Found {len(products)} products with selector: {selector}")
                break
        
        if not products:
            logger.warning("No products found with any selector")
            return results
        
        # Increase number of products to process
        for product in products[:10]:  # Changed from 5 to 10
            try:
                # Multiple selectors for title
                title = None
                title_selectors = [
                    "h2 a span",
                    "h2 span.a-text-normal",
                    "span.a-text-normal",
                    "a.a-link-normal span"
                ]
                for selector in title_selectors:
                    title = safe_get_text(product, selector)
                    if title:
                        break
                
                if not title:
                    continue
                
                # Multiple selectors for price
                price = 0.0
                price_selectors = [
                    "span.a-price span.a-offscreen",
                    "span.a-price-whole",
                    "span.a-price"
                ]
                for selector in price_selectors:
                    price_text = safe_get_text(product, selector)
                    if price_text:
                        price = extract_price(price_text)
                        if price > 0:
                            break
                
                if price == 0:
                    continue
                
                # Multiple selectors for URL
                url = None
                url_selectors = [
                    "h2 a",
                    "a.a-link-normal",
                    "a[href*='/dp/']"
                ]
                for selector in url_selectors:
                    url = safe_get_attribute(product, selector, "href")
                    if url:
                        if not url.startswith("http"):
                            url = f"https://www.amazon.com{url}"
                        break
                
                if not url:
                    continue
                
                # Get image URL
                image = safe_get_attribute(product, "img.s-image", "src")
                if not image:
                    image = safe_get_attribute(product, "img[data-image-load]", "src")
                
                # Get rating
                rating = None
                rating_text = safe_get_text(product, "span.a-icon-alt")
                if rating_text:
                    try:
                        rating = float(rating_text.split()[0])
                    except:
                        pass
                
                # Get reviews count
                reviews_count = None
                reviews_text = safe_get_text(product, "span.a-size-base.s-underline-text")
                if reviews_text:
                    try:
                        reviews_count = int(reviews_text.replace(",", ""))
                    except:
                        pass
                
                results.append(ProductResult(
                    title=title,
                    price=price,
                    url=url,
                    source="Amazon",
                    image_url=image,
                    rating=rating,
                    reviews_count=reviews_count
                ))
                logger.info(f"Successfully scraped product: {title[:50]}...")
                
            except Exception as e:
                logger.error(f"Error scraping Amazon product: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"Error scraping Amazon: {str(e)}")
    
    logger.info(f"Successfully scraped {len(results)} products from Amazon")
    return results

def scrape_walmart(driver: webdriver.Chrome, query: str) -> List[ProductResult]:
    results = []
    try:
        url = f"https://www.walmart.com/search?q={query.replace(' ', '+')}"
        logger.info(f"Scraping Walmart: {url}")
        
        # Add longer random delay before request
        time.sleep(random.uniform(3, 5))
        
        # Clear cookies and local storage before visiting
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        driver.delete_all_cookies()
        
        # Set up custom headers
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'User-Agent': get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
            }
        })
        
        # Navigate to the URL
        driver.get(url)
        logger.info("Navigated to Walmart search page")
        
        # Wait for page load with multiple selectors
        wait = WebDriverWait(driver, 20)
        content_selectors = [
            "div[data-item-id]",
            "div[data-testid='search-results']",
            "section[data-testid='search-results']",
            "div[class*='SearchResultsGridView']"
        ]
        
        found_content = False
        for selector in content_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                found_content = True
                logger.info(f"Found Walmart content with selector: {selector}")
                break
            except:
                continue
        
        if not found_content:
            logger.warning("Could not find Walmart search results")
            return results
        
        # Scroll to load more products
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 1000)")
            time.sleep(1)
        
        # Try different product selectors
        product_selectors = [
            "div[data-item-id]",
            "div[data-testid='search-result']",
            "div[class*='SearchResultsGridView'] > div",
            "div[data-automation-id='product']"
        ]
        
        products = []
        for selector in product_selectors:
            try:
                products = driver.find_elements(By.CSS_SELECTOR, selector)
                if products:
                    logger.info(f"Found {len(products)} Walmart products with selector: {selector}")
                    break
            except Exception as e:
                logger.error(f"Error with selector {selector}: {str(e)}")
                continue
        
        if not products:
            logger.warning("No Walmart products found after trying all selectors")
            return results
        
        # Process found products
        for product in products[:15]:  # Increased to 15 products
            try:
                # Scroll product into view
                driver.execute_script("arguments[0].scrollIntoView(true);", product)
                time.sleep(0.5)
                
                # Get title with multiple selectors
                title = None
                title_selectors = [
                    "span[data-automation-id='product-title']",
                    "span.w_kV",
                    "div[class*='heading'] span",
                    "a[class*='product-title-link']",
                    "*[class*='title']"
                ]
                
                for selector in title_selectors:
                    try:
                        title_elem = product.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        if title:
                            break
                    except:
                        continue
                
                if not title:
                    logger.warning("Could not find title for Walmart product")
                    continue
                
                # Get price with multiple selectors
                price = 0.0
                price_selectors = [
                    "div[data-automation-id='product-price']",
                    "span[class*='price-characteristic']",
                    "span[class*='price']",
                    "div[class*='price-box']",
                    "*[class*='price']"
                ]
                
                for selector in price_selectors:
                    try:
                        price_elem = product.find_element(By.CSS_SELECTOR, selector)
                        price_text = price_elem.text
                        price = extract_price(price_text)
                        if price > 0:
                            break
                    except:
                        continue
                
                if price == 0:
                    logger.warning("Could not find valid price for Walmart product")
                    continue
                
                # Get URL with multiple selectors
                url = None
                url_selectors = [
                    "a[link-identifier='linkText']",
                    "a[class*='product-title-link']",
                    "a[href*='/ip/']",
                    "a"
                ]
                
                for selector in url_selectors:
                    try:
                        url_elem = product.find_element(By.CSS_SELECTOR, selector)
                        url = url_elem.get_attribute("href")
                        if url and url.startswith("http"):
                            break
                    except:
                        continue
                
                if not url:
                    logger.warning("Could not find URL for Walmart product")
                    continue
                
                # Get image URL
                image_url = None
                try:
                    img_elem = product.find_element(By.CSS_SELECTOR, "img")
                    image_url = img_elem.get_attribute("src")
                except:
                    pass
                
                # Get rating and reviews count
                rating = None
                reviews_count = None
                try:
                    rating_elem = product.find_element(By.CSS_SELECTOR, "span[class*='rating']")
                    rating_text = rating_elem.get_attribute("aria-label")
                    if rating_text:
                        rating_match = re.search(r'(\d+(\.\d+)?)', rating_text)
                        if rating_match:
                            rating = float(rating_match.group(1))
                        
                        reviews_match = re.search(r'(\d+)\s+reviews?', rating_text)
                        if reviews_match:
                            reviews_count = int(reviews_match.group(1))
                except:
                    pass
                
                results.append(ProductResult(
                    title=title,
                    price=price,
                    url=url,
                    source="Walmart",
                    image_url=image_url,
                    rating=rating,
                    reviews_count=reviews_count
                ))
                logger.info(f"Successfully scraped Walmart product: {title[:50]}...")
                
            except Exception as e:
                logger.error(f"Error processing Walmart product: {str(e)}")
                continue
        
    except Exception as e:
        logger.error(f"Error scraping Walmart: {str(e)}")
        logger.exception(e)
    
    logger.info(f"Successfully scraped {len(results)} products from Walmart")
    return results

def scrape_target(driver: webdriver.Chrome, query: str) -> List[ProductResult]:
    results = []
    try:
        url = f"https://www.target.com/s?searchTerm={query.replace(' ', '+')}"
        logger.info(f"Scraping Target: {url}")
        
        # Add longer random delay before request
        time.sleep(random.uniform(3, 5))
        
        # Clear cookies and local storage before visiting
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        driver.delete_all_cookies()
        
        # Add additional headers
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": get_random_user_agent()
        })
        
        driver.get(url)
        
        # Wait for any of these elements to appear
        selectors = [
            "[data-test='product-grid']",
            "[data-test='product-card']",
            "[data-test='product-results']"
        ]
        
        found_element = False
        for selector in selectors:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                found_element = True
                logger.info(f"Found Target page content with selector: {selector}")
                break
            except:
                continue
        
        if not found_element:
            logger.warning("Could not verify Target page load")
            return results
        
        # Scroll down to load more products
        for _ in range(3):  # Scroll 3 times
            driver.execute_script("window.scrollBy(0, 800)")
            time.sleep(1)
        
        # Try to find products with different approaches
        products = []
        product_selectors = [
            "[data-test='product-card']",
            "[data-test='product-grid'] > div",
            "div[data-test='product-card-default']"
        ]
        
        for selector in product_selectors:
            try:
                products = driver.find_elements(By.CSS_SELECTOR, selector)
                if len(products) > 0:
                    logger.info(f"Found {len(products)} Target products with selector: {selector}")
                    break
            except Exception as e:
                logger.error(f"Error finding Target products with selector {selector}: {str(e)}")
                continue
        
        if not products:
            logger.warning("No Target products found")
            return results
        
        # Process more products
        for product in products[:10]:  # Changed from 5 to 10
            try:
                # Wait for product to be interactive
                driver.execute_script("arguments[0].scrollIntoView(true);", product)
                time.sleep(0.5)
                
                # Get title
                title = None
                title_selectors = [
                    "[data-test='product-title']",
                    "a[href*='/p/']",
                    "div[class*='Heading']"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = product.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        if title:
                            break
                    except:
                        continue
                
                if not title:
                    continue
                
                # Get price
                price = 0.0
                price_selectors = [
                    "[data-test='product-price']",
                    "span[data-test='current-price']",
                    "div[data-test='product-price']"
                ]
                for selector in price_selectors:
                    try:
                        price_elem = product.find_element(By.CSS_SELECTOR, selector)
                        price = extract_price(price_elem.text)
                        if price > 0:
                            break
                    except:
                        continue
                
                if price == 0:
                    continue
                
                # Get URL
                url = None
                url_selectors = [
                    "a[href*='/p/']",
                    "[data-test='product-title'] a",
                    "a[data-test='product-link']"
                ]
                for selector in url_selectors:
                    try:
                        url_elem = product.find_element(By.CSS_SELECTOR, selector)
                        url = url_elem.get_attribute("href")
                        if url:
                            break
                    except:
                        continue
                
                if not url or not url.startswith("http"):
                    continue
                
                results.append(ProductResult(
                    title=title,
                    price=price,
                    url=url,
                    source="Target",
                    image_url=None
                ))
                logger.info(f"Successfully scraped Target product: {title[:50]}...")
                
            except Exception as e:
                logger.error(f"Error scraping Target product: {str(e)}")
                continue
        
    except Exception as e:
        logger.error(f"Error scraping Target: {str(e)}")
    
    return results

# Create scheduler
scheduler = BackgroundScheduler()
scheduler.start()

@app.get("/search/{query}")
async def search_products(query: str):
    driver = None
    try:
        logger.info(f"Received search request for: {query}")
        driver = setup_driver()
        
        # Scrape from all sources
        amazon_results = scrape_amazon(driver, query)
        logger.info(f"Found {len(amazon_results)} Amazon products")
        
        # Add delay between scraping different sites
        time.sleep(random.uniform(2, 3))
        walmart_results = scrape_walmart(driver, query)
        logger.info(f"Found {len(walmart_results)} Walmart products")
        
        time.sleep(random.uniform(2, 3))
        target_results = scrape_target(driver, query)
        logger.info(f"Found {len(target_results)} Target products")
        
        # Combine all results
        all_results = amazon_results + walmart_results + target_results
        
        # Sort all results by price
        sorted_results = sorted(all_results, key=lambda x: x.price)
        
        logger.info(f"Total products found: {len(sorted_results)}")
        
        return {"results": sorted_results}
        
    except Exception as e:
        logger.error(f"Error in search_products: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed successfully")
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")

async def check_price_for_alert(alert_id: int, db: Session):
    try:
        # Get alert from database
        alert = db.query(PriceAlert).filter(PriceAlert.id == alert_id).first()
        if not alert or not alert.is_active:
            return
        
        # Set up driver and scrape current price
        driver = setup_driver()
        try:
            if "amazon.com" in alert.product_url:
                results = scrape_amazon(driver, alert.product_title)
            elif "walmart.com" in alert.product_url:
                results = scrape_walmart(driver, alert.product_title)
            elif "target.com" in alert.product_url:
                results = scrape_target(driver, alert.product_title)
            else:
                logger.error(f"Unsupported website for alert {alert_id}")
                return
            
            if results:
                # Update current price
                current_price = min(r.price for r in results)
                alert.current_price = current_price
                alert.last_checked = datetime.utcnow()
                
                # Check if price dropped below target
                if current_price <= alert.target_price:
                    # Send email notification
                    try:
                        sent = send_price_alert(
                            alert.user_email,
                            alert.product_title,
                            current_price,
                            alert.target_price,
                            alert.product_url
                        )
                        if sent:
                            alert.last_notified = datetime.utcnow()
                    except Exception as e:
                        logger.error(f"Failed to send email for alert {alert_id}: {str(e)}")
                
                db.commit()
                
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Error checking price for alert {alert_id}: {str(e)}")

@app.post("/alerts/", response_model=AlertResponse)
async def create_alert(alert: AlertCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_alert = PriceAlert(
        user_email=alert.user_email,
        product_url=alert.product_url,
        product_title=alert.product_title,
        target_price=alert.target_price,
        current_price=float('inf')
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    
    # Schedule immediate price check
    background_tasks.add_task(check_price_for_alert, db_alert.id, db)
    
    # Schedule recurring price check every 6 hours
    scheduler.add_job(
        check_price_for_alert,
        'interval',
        hours=6,
        args=[db_alert.id, db],
        id=f'alert_{db_alert.id}'
    )
    
    return db_alert

@app.get("/alerts/", response_model=list[AlertResponse])
async def get_alerts(email: str, db: Session = Depends(get_db)):
    alerts = db.query(PriceAlert).filter(PriceAlert.user_email == email).all()
    return alerts

@app.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(PriceAlert).filter(PriceAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Remove scheduled job
    try:
        scheduler.remove_job(f'alert_{alert_id}')
    except:
        pass
    
    # Delete alert from database
    db.delete(alert)
    db.commit()
    return {"message": "Alert deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 