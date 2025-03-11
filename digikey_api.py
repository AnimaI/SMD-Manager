import requests
import json
import base64
import time
import logging
import urllib.parse
import os
from functools import lru_cache
import threading
import redis
from datetime import datetime

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('digikey_api')

# Digi-Key API credentials from environment variables
DIGIKEY_CLIENT_ID = os.environ.get('DIGIKEY_CLIENT_ID', "xJXLW87QHd1YqO92iEKmRmhbMFlBHCsu")
DIGIKEY_CLIENT_SECRET = os.environ.get('DIGIKEY_CLIENT_SECRET', "43KtoCkbkpv90fJu")
DIGIKEY_AUTH_URL = "https://api.digikey.com/v1/oauth2/token"
DIGIKEY_PRODUCT_DETAILS_URL = "https://api.digikey.com/products/v4/search/{product_number}/productdetails"

# Redis connection for better caching, if available
try:
    redis_client = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=int(os.environ.get('REDIS_DB', 0)),
        socket_timeout=5
    )
    # Test the connection
    redis_client.ping()
    USE_REDIS = True
    logger.info("Redis cache enabled")
except (redis.exceptions.ConnectionError, ImportError):
    USE_REDIS = False
    logger.info("Redis cache disabled, using in-memory cache")

# Thread-safe token storage
TOKEN_LOCK = threading.Lock()
DIGIKEY_ACCESS_TOKEN = None
DIGIKEY_TOKEN_EXPIRY = 0

# Implement Rate Limiting
RATE_LIMIT = 5  # Requests per second
RATE_WINDOW = 1  # Seconds
LAST_REQUEST_TIMES = []
RATE_LIMIT_LOCK = threading.Lock()

def apply_rate_limiting():
    """Implements rate limiting for API requests"""
    with RATE_LIMIT_LOCK:
        current_time = time.time()
        
        # Remove old requests from the time window
        while LAST_REQUEST_TIMES and LAST_REQUEST_TIMES[0] < current_time - RATE_WINDOW:
            LAST_REQUEST_TIMES.pop(0)
        
        # If the limit is reached, wait
        if len(LAST_REQUEST_TIMES) >= RATE_LIMIT:
            sleep_time = LAST_REQUEST_TIMES[0] + RATE_WINDOW - current_time
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                current_time = time.time()  # Update time after waiting
                
        # Add the current request
        LAST_REQUEST_TIMES.append(current_time)

# Function to check if a part number is a DigiKey number
def is_digikey_part_number(part_number):
    """Checks if a part number is a DigiKey number."""
    if not part_number:
        return False
    
    # Typical patterns for DigiKey numbers
    patterns = [
        "-ND",      # Ends with -ND
        "CT-ND",    # Ends with CT-ND
        "TR-ND",    # Ends with TR-ND
        "DKR-ND",   # Contains DKR-ND
        "-1-ND"     # Contains -1-ND
    ]
    
    # DigiKey numbers often start with digits followed by a dash
    starts_with_digit_dash = len(part_number) > 2 and part_number[0].isdigit() and "-" in part_number[:5]
    
    # Check if any of the patterns are in the number
    has_pattern = any(pattern in part_number for pattern in patterns)
    
    return starts_with_digit_dash or has_pattern

# Function to get an access token
def get_digikey_access_token():
    global DIGIKEY_ACCESS_TOKEN, DIGIKEY_TOKEN_EXPIRY
    
    with TOKEN_LOCK:
        # Check if a valid token exists
        current_time = time.time()
        if DIGIKEY_ACCESS_TOKEN and current_time < DIGIKEY_TOKEN_EXPIRY:
            return DIGIKEY_ACCESS_TOKEN
        
        # Check if a token is in the cache (if Redis is used)
        if USE_REDIS:
            cached_token = redis_client.get('digikey_access_token')
            cached_expiry = redis_client.get('digikey_token_expiry')
            
            if cached_token and cached_expiry:
                token_expiry = float(cached_expiry.decode('utf-8'))
                if current_time < token_expiry:
                    DIGIKEY_ACCESS_TOKEN = cached_token.decode('utf-8')
                    DIGIKEY_TOKEN_EXPIRY = token_expiry
                    return DIGIKEY_ACCESS_TOKEN
    
    try:
        # Client Credentials Flow for OAuth 2.0
        auth_header = base64.b64encode(f"{DIGIKEY_CLIENT_ID}:{DIGIKEY_CLIENT_SECRET}".encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}"
        }
        
        payload = {
            "grant_type": "client_credentials",
            "scope": "product.info"
        }
        
        # Apply Rate Limiting
        apply_rate_limiting()
        
        logger.info("Requesting new DigiKey access token")
        response = requests.post(DIGIKEY_AUTH_URL, headers=headers, data=payload)
        
        if response.status_code == 200:
            token_data = response.json()
            
            with TOKEN_LOCK:
                DIGIKEY_ACCESS_TOKEN = token_data["access_token"]
                # Store token expiry time (with some buffer)
                token_expiry = current_time + token_data["expires_in"] - 60
                DIGIKEY_TOKEN_EXPIRY = token_expiry
                
                # Cache in Redis, if available
                if USE_REDIS:
                    redis_client.set('digikey_access_token', DIGIKEY_ACCESS_TOKEN)
                    redis_client.set('digikey_token_expiry', str(token_expiry))
                    
                logger.info("Successfully obtained new DigiKey access token")
                return DIGIKEY_ACCESS_TOKEN
        
        logger.error(f"Token error: {response.status_code}, {response.text}")
        return None
    except Exception as e:
        logger.error(f"Token error: {str(e)}")
        return None

# Cache for product information
PRODUCT_CACHE = {}
PRODUCT_CACHE_LOCK = threading.Lock()

def get_cache_key(product_number):
    """Generates a unique cache key for the product"""
    return f"digi_product:{product_number}"

def get_cached_product(product_number):
    """Attempts to get the product from the cache"""
    cache_key = get_cache_key(product_number)
    
    # Try Redis first, if available
    if USE_REDIS:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError:
                pass
    
    # Otherwise get from local cache
    with PRODUCT_CACHE_LOCK:
        return PRODUCT_CACHE.get(product_number)

def set_product_cache(product_number, product_data):
    """Stores the product in the cache"""
    cache_key = get_cache_key(product_number)
    
    # Store in Redis, if available
    if USE_REDIS:
        redis_client.setex(
            cache_key,
            60 * 60 * 24,  # 24 hours TTL
            json.dumps(product_data)
        )
    
    # Also store in local cache
    with PRODUCT_CACHE_LOCK:
        PRODUCT_CACHE[product_number] = product_data

def encode_part_number(part_number):
    """Improved URL encoding for part numbers with special characters.
    Special attention to slashes and other special characters."""
    
    # DigiKey API has issues with certain characters, especially '/'
    # Replace special characters with appropriate URL encodings
    
    # Direct replacement of certain special characters before standard encoding
    replacements = {
        "/": "%2F",
        "+": "%2B",
        "&": "%26",
        "?": "%3F",
        "=": "%3D",
        "#": "%23",
        ";": "%3B",
        "$": "%24",
        ",": "%2C",
        " ": "%20",
        "<": "%3C",
        ">": "%3E"
    }
    
    # Perform for each special character
    for char, replacement in replacements.items():
        part_number = part_number.replace(char, replacement)
    
    # Additionally ensure everything is correctly encoded
    # Use secure encoding from urllib, treat everything as path segment
    encoded = urllib.parse.quote(part_number, safe='')
    
    return encoded

def fetch_digikey_product_info(digikey_number):
    """Retrieves product information from the DigiKey API, including description and manufacturer part number"""
    if not digikey_number:
        return None, "No DigiKey number provided"
        
    try:
        # Try to load from cache first
        cached_product = get_cached_product(digikey_number)
        if cached_product:
            logger.info(f"Cache hit for {digikey_number}")
            return cached_product.get('manufacturer_part_number'), cached_product.get('description')
            
        logger.info(f"Fetching product info for DigiKey number: {digikey_number}")
        access_token = get_digikey_access_token()
        if not access_token:
            logger.error("Failed to get access token")
            return None, "API access failed"
        
        # Improved URL encoding for part numbers with special characters
        encoded_number = encode_part_number(digikey_number)
        
        # API URL with product number
        url = DIGIKEY_PRODUCT_DETAILS_URL.format(product_number=encoded_number)
        
        headers = {
            "X-DIGIKEY-Client-Id": DIGIKEY_CLIENT_ID,
            "Authorization": f"Bearer {access_token}",
            "X-DIGIKEY-Locale-Site": "DE",
            "X-DIGIKEY-Locale-Language": "de",
            "X-DIGIKEY-Locale-Currency": "EUR"
        }
        
        # Apply Rate Limiting
        apply_rate_limiting()
        
        logger.info(f"API request for: {digikey_number} to URL: {url}")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            product_data = response.json()
            
            # Debugging: Output API response
            logger.info(f"API response received for {digikey_number}")
            
            # Extract information from the response
            manufacturer_part_number = None
            description = "No description available"
            
            if 'Product' in product_data:
                # Extract manufacturer part number
                if 'ManufacturerProductNumber' in product_data['Product']:
                    manufacturer_part_number = product_data['Product']['ManufacturerProductNumber']
                    logger.info(f"Found manufacturer part number: {manufacturer_part_number}")
                # Alternatively look for ManufacturerPartNumber (in case the format has changed)
                elif 'ManufacturerPartNumber' in product_data['Product']:
                    manufacturer_part_number = product_data['Product']['ManufacturerPartNumber']
                    logger.info(f"Found manufacturer part number (alternative path): {manufacturer_part_number}")
                
                # Extract description
                if 'Description' in product_data['Product']:
                    # Check if Description is a dictionary with ProductDescription
                    if isinstance(product_data['Product']['Description'], dict) and 'ProductDescription' in product_data['Product']['Description']:
                        description = product_data['Product']['Description']['ProductDescription']
                    # Alternatively, if Description directly contains the text
                    else:
                        description = product_data['Product']['Description']
                # Alternatively look for ProductDescription directly
                elif 'ProductDescription' in product_data['Product']:
                    description = product_data['Product']['ProductDescription']
                
                logger.info(f"Found description: {description}")
                
                # Store in cache
                cache_data = {
                    'manufacturer_part_number': manufacturer_part_number,
                    'description': description,
                    'timestamp': datetime.now().isoformat()
                }
                set_product_cache(digikey_number, cache_data)
                
            return manufacturer_part_number, description
        elif response.status_code == 429:
            # If rate limit reached, wait briefly and try again
            logger.warning("Rate limit reached, waiting before retry")
            time.sleep(2)
            return fetch_digikey_product_info(digikey_number)
        else:
            logger.error(f"Product API error: {response.status_code}, {response.text}")
            return None, f"Error retrieving: HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {str(e)}")
        return None, f"Network error: {str(e)}"
    except Exception as e:
        logger.error(f"Product API error: {str(e)}")
        return None, "API error: " + str(e)

# Improved function for DigiKey KeywordSearch API
@lru_cache(maxsize=128)
def search_digikey_keyword(keyword, limit=10):
    """
    Searches for a keyword in the DigiKey database using the KeywordSearch API
    
    Args:
        keyword (str): The keyword to search for (e.g., manufacturer part number)
        limit (int): Maximum number of results to return
        
    Returns:
        list: List of found products
    """
    if not keyword:
        return []
        
    # Cache key for this search
    cache_key = f"search:{keyword}:{limit}"
    
    # Get from Redis cache, if available
    if USE_REDIS:
        cached_results = redis_client.get(cache_key)
        if cached_results:
            try:
                return json.loads(cached_results)
            except json.JSONDecodeError:
                pass
    
    try:
        logger.info(f"Searching DigiKey for keyword: {keyword}")
        access_token = get_digikey_access_token()
        if not access_token:
            logger.error("Could not obtain access token")
            return []
        
        url = "https://api.digikey.com/products/v4/search/keyword"
        
        headers = {
            "X-DIGIKEY-Client-Id": DIGIKEY_CLIENT_ID,
            "Authorization": f"Bearer {access_token}",
            "X-DIGIKEY-Locale-Site": "DE",
            "X-DIGIKEY-Locale-Language": "de",
            "X-DIGIKEY-Locale-Currency": "EUR",
            "Content-Type": "application/json"
        }
        
        # Enhanced search options for more robust results
        search_options = []
        
        # If we suspect it's a DigiKey number, search for that
        if is_digikey_part_number(keyword):
            search_options.append("DigiKeyPartNumberSearch")
        else:
            # Otherwise we assume it's a manufacturer number
            search_options.append("ManufacturerPartSearch")
            
        # For more robust search results, add additional options
        search_options.append("DiscreteSearch")
        
        # Special handling for part numbers with slashes
        if '/' in keyword:
            # For part numbers with slash, try different variations
            # e.g., "MCP1824T-0802E/OTCT-ND" -> also search for "MCP1824T 0802E OTCT ND"
            search_keywords = [
                keyword,
                keyword.replace('/', ' '),  # Replace / with space
                keyword.replace('/', '-'),  # Replace / with dash
                keyword.replace('/', '')    # Remove /
            ]
        else:
            search_keywords = [keyword]
        
        # Collect results from all searches
        all_products = []
        
        for search_keyword in search_keywords:
            payload = {
                "Keywords": search_keyword,
                "Limit": limit,
                "SearchOptions": search_options,
                "ExcludeMarketplaceProducts": False,  # Include Marketplace products
                "RecordCount": limit,
                "RecordStartPosition": 0,
                "Filters": {
                    "AvailabilityFilter": 2  # In Stock + On Order
                }
            }
            
            logger.info(f"Sending KeywordSearch request for: {search_keyword}")
            logger.info(f"With SearchOptions: {search_options}")
            
            # Apply Rate Limiting
            apply_rate_limiting()
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                products = data.get('Products', [])
                logger.info(f"KeywordSearch response received for {search_keyword}: {len(products)} results")
                
                # For manufacturer number search: If no direct products but ProductDetails exists,
                # examine this object
                if len(products) == 0 and 'ProductDetails' in data:
                    product_details = data.get('ProductDetails')
                    if product_details:
                        products = [product_details]  # Return as list for consistent processing
                
                # Add products to the overall list
                all_products.extend(products)
            elif response.status_code == 429:
                # If rate limit reached, wait briefly and continue with the next search
                logger.warning("Rate limit reached, waiting before continuing")
                time.sleep(2)
            else:
                logger.error(f"DigiKey API Error for {search_keyword}: {response.status_code}, {response.text}")
                # Try to analyze the error
                try:
                    error_data = response.json()
                    logger.error(f"Error details: {error_data}")
                except:
                    pass
        
        # Deduplicate results
        unique_products = []
        seen_digi_keys = set()
        
        for product in all_products:
            # Extract DigiKey number
            digi_key_number = None
            if 'DigiKeyPartNumber' in product:
                digi_key_number = product['DigiKeyPartNumber']
            
            # Skip if no DigiKey number or already seen
            if not digi_key_number or digi_key_number in seen_digi_keys:
                continue
            
            seen_digi_keys.add(digi_key_number)
            unique_products.append(product)
        
        # Store in cache, if Redis is available
        if USE_REDIS and unique_products:
            redis_client.setex(
                cache_key,
                60 * 60,  # 1 hour TTL
                json.dumps(unique_products)
            )
        
        logger.info(f"Final unique products count: {len(unique_products)}")
        return unique_products
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"KeywordSearch error: {str(e)}")
        return []

# Helper function for uniform extraction of product data
def extract_product_data(product):
    """
    Extracts important data uniformly from a DigiKey product object
    
    Args:
        product (dict): The product object from the DigiKey API
        
    Returns:
        tuple: (digikey_number, manufacturer_number, description)
    """
    if not product or not isinstance(product, dict):
        return "", "", ""
        
    try:
        # Initialize default values
        digikey_number = ""
        manufacturer_number = ""
        description = ""
        
        # Extract manufacturer number
        if 'ManufacturerPartNumber' in product:
            manufacturer_number = product['ManufacturerPartNumber']
        elif 'ManufacturerProductNumber' in product:
            manufacturer_number = product['ManufacturerProductNumber']
        
        # Extract DigiKey number - directly or from ProductVariations
        if 'DigiKeyPartNumber' in product:
            digikey_number = product['DigiKeyPartNumber']
        # When searching for a manufacturer number, the DigiKey number might be
        # in the ProductVariations
        elif 'ProductVariations' in product and product['ProductVariations']:
            # Take the first or the CT (Cut Tape) variation, if available
            variations = product['ProductVariations']
            ct_variation = next((v for v in variations if 'PackageType' in v and 
                            isinstance(v['PackageType'], dict) and
                            v['PackageType'].get('Name', '').lower() == 'cut tape (ct)'), None)
            
            if ct_variation and 'DigiKeyProductNumber' in ct_variation:
                digikey_number = ct_variation['DigiKeyProductNumber']
            elif variations[0].get('DigiKeyProductNumber'):
                digikey_number = variations[0]['DigiKeyProductNumber']
        
        # Extract description
        if 'ProductDescription' in product:
            description = product['ProductDescription']
        elif 'Description' in product:
            if isinstance(product['Description'], dict) and 'ProductDescription' in product['Description']:
                description = product['Description']['ProductDescription']
            else:
                description = str(product['Description'])
        elif 'DetailedDescription' in product:
            description = product['DetailedDescription']
        
        # Log the extracted values
        logger.debug(f"Extracted data: DK={digikey_number}, MPN={manufacturer_number}, Desc={description[:30]}...")
        
        return digikey_number, manufacturer_number, description
    except Exception as e:
        logger.error(f"Error extracting product data: {str(e)}")
        return '', '', ''

# The previous fetch_digikey_description function, but now calls the new function
def fetch_digikey_description(digikey_number):
    """Just retrieves the description (for compatibility with existing code)"""
    _, description = fetch_digikey_product_info(digikey_number)
    return description