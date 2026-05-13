import requests
import os
import pyotp
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys
import datetime
import time
import schedule
from dotenv import load_dotenv
import pandas_ta as ta
from datetime import timedelta
from dateutil import parser as date_parser
import pytz  # Add pytz for timezone handling
import logging
from logging.handlers import RotatingFileHandler
from select_option import OptionsDataFetcher
import traceback
import pandas_ta as ta

# Fix UnicodeEncodeError for Windows
sys.stdout.reconfigure(encoding='utf-8')

# Project root (one level above the api/ folder) – used for the session logs dir
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

def setup_logger(log_level=logging.INFO, session_log_path=None):
    """Setup and configure the logger with console output, optionally adding a
    per-session file handler that writes to ``session_log_path``."""
    logger = logging.getLogger("angelone_trader")
    logger.setLevel(log_level)

    if logger.handlers:
        for handler in logger.handlers:
            try:
                handler.close()
            except Exception:
                pass
        logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if session_log_path:
        os.makedirs(os.path.dirname(session_log_path), exist_ok=True)
        file_handler = logging.FileHandler(session_log_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# Initialize logger
logger = setup_logger()

# Load environment variables from .env file
logger.info("🔍 Loading environment variables from .env file...")
load_dotenv()

# Angel One API credentials
CLIENT_ID = os.getenv("ANGELONE_CLIENT_ID")
PASSWORD = os.getenv("ANGELONE_MPIN")
TOTP_SECRET = os.getenv("ANGELONE_TOTP_SECRET")

logger.info(f"🔐 Credentials loaded - Client ID: {CLIENT_ID}, TOTP Secret: {'*' if TOTP_SECRET else 'Not found'}")

# Global variables
auth_token = None
headers = None
auth_time = None
auth_valid_duration = 6 * 60 * 60  # 6 hours in seconds
active_position = None
entry_price = None
trade_history = []
total_profit_loss = 0
current_trade_entry_price = None
current_trade_entry_time = None
trade_count = 0
winning_trades = 0
losing_trades = 0
API_KEY = None
duration = "DAY"
trading_symbol = None
symbol_token = None
exchange = None
quantity = None
instrument_type = ''
option_data = None
SUPERTREND_LENGTH = 10 
SUPERTREND_FACTOR = 2.0  
#status_message = None  # Global variable to store status messages

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')

# Helper function to get current time in IST
def get_ist_now():
    """Returns current time in Indian Standard Time"""
    return datetime.datetime.now(IST).replace(tzinfo=None)

# Candle configuration
CANDLE_SIZE_SECONDS = {
    "ONE_MINUTE": 60,
    "FIVE_MINUTE": 300,
    "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800,
    "ONE_HOUR": 3600,
    "ONE_DAY": 86400
}

def get_candle_size(duration_minutes):
    """Convert duration in minutes to Angel One's candle size format"""
    if duration_minutes == 1:
        return "ONE_MINUTE"
    elif duration_minutes == 5:
        return "FIVE_MINUTE"
    elif duration_minutes == 15:
        return "FIFTEEN_MINUTE"
    elif duration_minutes == 30:
        return "THIRTY_MINUTE"
    elif duration_minutes == 60:
        return "ONE_HOUR"
    elif duration_minutes == 1440:  # 24 hours
        return "ONE_DAY"
    else:
        raise ValueError(f"Unsupported candle duration: {duration_minutes} minutes")

# Function to get authentication token with reuse logic
def get_auth_token(force_new=False):
    """Get authentication token with reuse logic"""
    global auth_token, headers, auth_time
    
    # If we have valid headers and not forcing a refresh, reuse them
    if headers and auth_time and not force_new:
        elapsed = (get_ist_now() - auth_time).total_seconds()
        if elapsed < auth_valid_duration:
            logger.debug("🔄 Reusing existing auth token")
            return headers
    
    logger.info("\n🔐 Getting fresh auth token from Angel One API...")
    
    # Prepare request headers
    headers = {
        "Content-type": "application/json",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00",
        "Accept": "application/json",
        "X-PrivateKey": API_KEY,
        "X-UserType": "USER",
        "X-SourceID": "WEB"
    }
    
    # Generate TOTP
    totp = pyotp.TOTP(TOTP_SECRET).now()
    
    # Login payload
    payload = {
        "clientcode": CLIENT_ID,
        "password": PASSWORD,
        "totp": totp
    }
    
    url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
    
    try:
        logger.info("📡 Sending login request to Angel One API...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.info(f"🔔 Received response with status code: {response.status_code}")
        
        response_data = response.json()
        if response_data.get("status") and response_data.get("data"):
            auth_token = response_data["data"]["jwtToken"]
            headers["Authorization"] = f"Bearer {auth_token}"
            auth_time = get_ist_now()
            logger.info("✅ Authentication successful, token obtained")
            return headers
        else:
            logger.error(f"❌ Login failed: {response_data}")
            return None
    except Exception as e:
        logger.error(f"⚠ Error during authentication: {e}")
        logger.debug(traceback.format_exc())
        return None

# Format timestamp from API response
def format_timestamp(ts_str):
    """Convert ISO timestamp to a cleaner format"""
    try:
        # Parse the ISO timestamp using date_parser instead of parser
        dt = date_parser.parse(ts_str)
        # Format as YYYY-MM-DD HH:MM:SS
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.error(f"⚠ Could not parse timestamp {ts_str}: {e}")
        return ts_str  # Return original if parsing fails

# Enhanced candle fetching function with timezone fix
def fetch_candle(target_minute, symbol_token, exchange, check_type="FINAL", max_retries=3, retry_delay=1):
    """
    Fetch a specific candle from Angel One API with retry mechanism
    Args:
        target_minute: Target minute to fetch candle for
        symbol_token: Symbol token
        exchange: Exchange
        check_type: Type of check (FINAL, REGULAR, etc.)
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    Returns:
        dict: Candle data or None if all retries fail
    """
    headers = get_auth_token()
    if not headers:
        logger.error("❌ Failed to get auth token, skipping candle fetch")
        return None
    
    #from_date = target_minute.strftime("%Y-%m-%d %H:%M")
    from_datetime = target_minute

    if CANDLE_SIZE == "FIVE_MINUTE":
        # For 5-minute candles, we need to fetch from start to end of the 5-minute period
        to_datetime = target_minute + timedelta(minutes=5)
    else:
        # For 1-minute candles
        to_datetime = target_minute + timedelta(minutes=1)

    from_date = from_datetime.strftime("%Y-%m-%d %H:%M")
    to_date = to_datetime.strftime("%Y-%m-%d %H:%M")

    # Convert seconds to interval string format
    interval_seconds = CANDLE_SIZE_SECONDS.get(CANDLE_SIZE, 60)
    interval_string = None
    
    if interval_seconds == 60:
        interval_string = "ONE_MINUTE"
    elif interval_seconds == 300:
        interval_string = "FIVE_MINUTE"
    elif interval_seconds == 900:
        interval_string = "FIFTEEN_MINUTE"
    elif interval_seconds == 1800:
        interval_string = "THIRTY_MINUTE"
    elif interval_seconds == 3600:
        interval_string = "ONE_HOUR"
    elif interval_seconds == 86400:
        interval_string = "ONE_DAY"
    else:
        logger.error(f"❌ Unsupported interval: {interval_seconds} seconds")
        return None
    
    payload = {
        "exchange": exchange,
        "symboltoken": symbol_token,
        "interval": interval_string,  # Using string format instead of seconds
        "fromdate": from_date,
        "todate": to_date
    }
    logger.info(f"📊 Payload for Live Candle API request: {payload}")
    url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"📡 Fetching {check_type} candle for {from_date} (Attempt {attempt + 1}/{max_retries})")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            # Handle unauthorized errors (token expired)
            if response.status_code == 401:
                logger.warning("⚠ Auth token expired, refreshing...")
                headers = get_auth_token(force_new=True)
                if headers:
                    continue  # Retry with new token
                else:
                    return None
            
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") and data.get("data"):
                candles = data["data"]
                if candles and len(candles) > 0:
                    candle = candles[0]
                    original_timestamp = candle[0]
                    formatted_timestamp = format_timestamp(original_timestamp)
                    
                    dt = pd.to_datetime(formatted_timestamp).replace(tzinfo=None)
                    
                    candle_data = {
                        'date': dt,
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': int(candle[5])
                    }
                    
                    logger.debug(f"📊 {check_type} Candle @ {formatted_timestamp} — "
                          f"O:{candle_data['open']:.2f} H:{candle_data['high']:.2f} "
                          f"L:{candle_data['low']:.2f} C:{candle_data['close']:.2f} "
                          f"V:{candle_data['volume']}")
                    
                    return candle_data
                else:
                    logger.warning(f"⚠ No {check_type} candle data returned for {from_date}")
            else:
                if "token" in str(data).lower() or "auth" in str(data).lower():
                    logger.warning("⚠ Token error detected, refreshing...")
                    get_auth_token(force_new=True)
                logger.error(f"❌ API returned error for {check_type} check: {data}")
            
            # If we get here, the attempt failed but wasn't an exception
            if attempt < max_retries - 1:
                logger.warning(f"⚠ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Network error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"⚠ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue
        except Exception as e:
            logger.error(f"❌ Error fetching {check_type} candle: {str(e)}")
            logger.debug(traceback.format_exc())
            if attempt < max_retries - 1:
                logger.warning(f"⚠ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue
    
    logger.error(f"❌ Failed to fetch {check_type} candle after {max_retries} attempts")
    return None

# Function to fetch the latest completed candle
def fetch_latest_candle(symbol_token, exchange, max_retries=3, retry_delay=1):
    """Fetch the latest completed candle with retry mechanism"""
    now = get_ist_now()
    last_minute = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
    
    return fetch_candle(last_minute, symbol_token, exchange, "LATEST", max_retries, retry_delay)

# Login and setup
def login_to_angel_one(api_token=None):
    """Authenticate with Angel One API"""
    global API_KEY
    
    API_KEY = api_token
    logger.info(f"🔑 Using API key: {API_KEY}")
    
    # Get authentication token
    headers = get_auth_token(force_new=True)
    return headers is not None

# Logout implementation
def logout_from_angel_one():
    """Logout from Angel One API"""
    global headers

    logger.info("\n🔐 Attempting to logout from Angel One API...")
    url = "https://apiconnect.angelone.in/rest/secure/angelbroking/user/v1/logout"
    payload = {"clientcode": CLIENT_ID}

    try:
        logger.info("📡 Sending logout request...")
        response = requests.post(url, json=payload, headers=headers)
        logger.info(f"🔔 Received response with status code: {response.status_code}")
        
        response_data = response.json()
        logger.debug(f"📋 Response data: {response_data}")

        if response_data.get("status"):
            logger.info("✅ Logout successful!")
            return True
        else:
            logger.error(f"❌ Logout failed. Error: {response_data.get('message')}")
            return False
    except Exception as e:
        logger.error(f"⚠ Error during logout: {str(e)}")
        logger.debug(traceback.format_exc())
        return False

# Enhanced historical data fetching with timezone fix
def fetch_historical_stock_data(symbol_token, exchange, max_retries=3, retry_delay=1):
    """Fetch historical stock data from Angel One API combining current and previous session data with retry mechanism"""
    #global status_message
    logger.info("\n📜 Fetching historical stock data...")
    try:
        now = get_ist_now()
        today = now.date()
        current_time = now.time()
        
        # Define market hours
        market_open = datetime.time(9, 15)
        market_close = datetime.time(15, 30)
        
        # Determine if market is currently open
        market_is_open = (now.weekday() < 5) and (market_open <= current_time <= market_close)
        logger.info(f"🕒 Market status check - Weekday: {now.weekday()}, Current time: {current_time}, Market open: {market_is_open}")
        
        # Initialize DataFrame for current session
        current_session_data = None
        previous_session_data = None
        
        # First try to get current session data if market is open
        # if market_is_open:  # Commented out as requested
        # For current session, only fetch up to the last completed candle
        current_from_date = today.strftime("%Y-%m-%d") + " 09:15"
        
        # Calculate the last completed candle time
        if CANDLE_SIZE == "ONE_MINUTE":
            # For 1-minute candles, go back 1 minute
            current_to_date = (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
        else:
            # For 5-minute candles, go back to the last completed 5-minute boundary
            # If current minute is 10:19, we want to fetch up to 10:10
            # If current minute is 10:20, we want to fetch up to 10:15
            # If current minute is 10:21, we want to fetch up to 10:15
            current_minute = now.minute
            # Calculate the most recent completed 5-minute candle boundary
            last_boundary = (current_minute // 5) * 5
            if current_minute % 5 == 0:  # If we're exactly at a boundary, we need the previous one
                last_boundary = last_boundary - 5

            # Set time to the last completed candle boundary
            current_to_date = now.replace(minute=last_boundary, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
            logger.info(f"⏳ Adjusted current_to_date for {CANDLE_SIZE} candles: {current_to_date}")
        
        logger.info(f"📅 Fetching current session data from {current_from_date} to {current_to_date}")
        
        # Retry loop for current session data
        for attempt in range(max_retries):
            try:
                current_data = fetch_session_data(symbol_token, exchange, current_from_date, current_to_date)
                if current_data is not None and not current_data.empty:
                    current_session_data = current_data
                    logger.info(f"📊 Fetched {len(current_data)} candles from current session")
                    break
                else:
                    logger.warning(f"⚠ No data returned for current session (Attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
            except Exception as e:
                logger.error(f"❌ Error fetching current session data (Attempt {attempt + 1}/{max_retries}): {str(e)}")
                logger.debug(traceback.format_exc())
                if attempt < max_retries - 1:
                    logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
    
        # Only fetch previous session data if we have less than 60 candles in current session
        # or if current session data fetch failed
        if current_session_data is None or len(current_session_data) < 60:
            if current_session_data is None:
                logger.info("⚠️ Current session data fetch failed, fetching previous session data...")
            else:
                logger.info(f"⚠️ Current session has only {len(current_session_data)} candles, fetching previous session data...")
            
            # Get previous session data
            days_to_subtract = 1
            if now.weekday() == 5:  # Saturday
                days_to_subtract = 1
            elif now.weekday() == 6:  # Sunday
                days_to_subtract = 2
            elif now.weekday() == 0:  # Monday
                days_to_subtract = 3
            
            prev_trading_date = today - datetime.timedelta(days=days_to_subtract)
            prev_from_date = prev_trading_date.strftime("%Y-%m-%d") + " 09:15"
            prev_to_date = prev_trading_date.strftime("%Y-%m-%d") + " 15:30"
            
            # Retry loop for previous session data
            for attempt in range(max_retries):
                try:
                    previous_session_data = fetch_session_data(symbol_token, exchange, prev_from_date, prev_to_date)
                    if previous_session_data is not None and not previous_session_data.empty:
                        logger.info(f"📊 Fetched {len(previous_session_data)} candles from previous session")
                        break
                    else:
                        logger.warning(f"⚠ No data returned for previous session (Attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            continue
                except Exception as e:
                    logger.error(f"❌ Error fetching previous session data (Attempt {attempt + 1}/{max_retries}): {str(e)}")
                    logger.debug(traceback.format_exc())
                    if attempt < max_retries - 1:
                        logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
        
        # Combine data ensuring current session data comes first
        if current_session_data is not None and previous_session_data is not None:
            # Explicitly combine with current session first, then previous session
            df = pd.concat([current_session_data, previous_session_data])
            logger.info("📊 Combined current and previous session data.")
        elif current_session_data is not None:
            df = current_session_data
            logger.info("📊 Using only current session data as previous session data is not available.")
        elif previous_session_data is not None:
            df = previous_session_data
            logger.info("📊 Using only previous session data as current session data is not available.")
        else:
            df = None
            #status_message = "Error fetching historical data: Check whether the correct stock name is inputted or contact developer for further assistance."
            logger.error("❌ No data available from either session.")

        # Sort by date to ensure chronological order
        if df is not None:
            df = df.sort_index()
            logger.info(f"📊 Final dataset: {len(df)} candles from {df.index.min()} to {df.index.max()}")

            # Show last 15 candles before returning
            logger.info("📊 Last 15 candles:")
            logger.info(f"\n{df.tail(15).to_string()}")
        
        return df
    
    except Exception as e:
        #status_message = f"Error fetching historical data: Check whether the correct stock name is inputted or contact developer for further assistance."
        logger.error(f"⚠ Error fetching historical data: {str(e)}")
        return None
    
def fetch_session_data(symbol_token, exchange, from_date, to_date):
    """Helper function to fetch data for a specific session"""
    # Convert seconds to interval string format
    interval_seconds = CANDLE_SIZE_SECONDS.get(CANDLE_SIZE, 60)
    interval_string = None
    
    if interval_seconds == 60:
        interval_string = "ONE_MINUTE"
    elif interval_seconds == 300:
        interval_string = "FIVE_MINUTE"
    elif interval_seconds == 900:
        interval_string = "FIFTEEN_MINUTE"
    elif interval_seconds == 1800:
        interval_string = "THIRTY_MINUTE"
    elif interval_seconds == 3600:
        interval_string = "ONE_HOUR"
    elif interval_seconds == 86400:
        interval_string = "ONE_DAY"
    else:
        logger.error(f"❌ Unsupported interval: {interval_seconds} seconds")
        return None

    payload = {
        "exchange": exchange,
        "symboltoken": symbol_token,
        "interval": interval_string,  # Using string format instead of seconds
        "fromdate": from_date,
        "todate": to_date
    }
    logger.info(f"📊 Payload for Historical Data API request: {payload}")
    url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
    
    try:
        headers = get_auth_token()
        if not headers:
            return None
            
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 401:
            headers = get_auth_token(force_new=True)
            if headers:
                response = requests.post(url, json=payload, headers=headers)
            else:
                return None
        
        response_data = response.json()
        
        if "data" in response_data and response_data["data"]:
            df = pd.DataFrame(response_data["data"], columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
            
            # Filter market hours
            df["time"] = df["date"].dt.time
            df = df[(df["time"] >= datetime.time(9, 15)) & (df["time"] <= datetime.time(15, 30))]
            df = df.drop(columns=["time"])
            
            df.set_index("date", inplace=True)
            return df
            
    except Exception as e:
        logger.error(f"⚠ Error fetching session data: {str(e)}")
        logger.debug(traceback.format_exc())
    
    return None

# Fixed Supertrend calculation function
def calculate_supertrend(df):
    """Calculate supertrend indicator with custom parameters"""
    global SUPERTREND_LENGTH, SUPERTREND_FACTOR
    
    logger.info("\n📈 Calculating Supertrend indicator...")
    if df is None or df.empty:
        logger.error("❌ No data available for Supertrend calculation")
        return None
    
    df_copy = df.copy()
    logger.debug(f"📊 Input DataFrame shape: {df_copy.shape}")
    
    # Ensure all required columns exist and are numeric
    required_cols = ["open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df_copy.columns:
            logger.error(f"❌ Missing column: {col} for Supertrend calculation")
            return None
        df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
    
    df_copy = df_copy.dropna(subset=required_cols)
    logger.debug(f"📊 DataFrame after dropping NA: {df_copy.shape}")
    
    if len(df_copy) < SUPERTREND_LENGTH:  # Use dynamic length
        logger.error(f"❌ Not enough data points for Supertrend calculation (need at least {SUPERTREND_LENGTH})")
        return df_copy
    
    try:
        logger.info(f"🔧 Calculating Supertrend with length={SUPERTREND_LENGTH}, multiplier={SUPERTREND_FACTOR}...")
        supertrend = ta.supertrend(
            df_copy['high'], 
            df_copy['low'], 
            df_copy['close'], 
            length=SUPERTREND_LENGTH,  # Use dynamic length
            multiplier=SUPERTREND_FACTOR  # Use dynamic factor
        )
        #logger.info(f"📊 Supertrend calculation result: {supertrend}")
        if supertrend is not None:
            logger.info("✅ Supertrend calculation successful")
            
            # Remove any existing supertrend columns
            for col in df_copy.columns:
                if col.startswith('SUPERT_'):
                    df_copy = df_copy.drop(columns=[col])
                    logger.debug(f"♻ Removed existing column: {col}")
            
            df_copy = pd.concat([df_copy, supertrend], axis=1)
            logger.debug("📊 DataFrame after adding Supertrend columns:")
            logger.debug(f"\n{df_copy.tail().to_string()}")
            
            # The column name depends on the parameters
            supertrend_col = f"SUPERT_{SUPERTREND_LENGTH}_{SUPERTREND_FACTOR}"
            
            # Align series before comparison
            close_series = df_copy['close']
            supertrend_series = df_copy[supertrend_col]
            close_series, supertrend_series = close_series.align(supertrend_series, join='inner')
            
            # Create signal column
            df_copy['signal'] = np.where(close_series > supertrend_series, 'buy', 'sell')
            df_copy['signal_change'] = (df_copy['signal'] != df_copy['signal'].shift(1)) & (df_copy['signal'].shift(1).notna())
            
            logger.info("📈 Signal column created:")
            logger.debug(f"\n{df_copy[['close', supertrend_col, 'signal', 'signal_change']].tail().to_string()}")
        else:
            logger.error("❌ Supertrend calculation returned None")
    except Exception as e:
        logger.error(f"❌ Error calculating Supertrend: {e}")
        logger.debug(traceback.format_exc())
    
    return df_copy

def plot_data_with_supertrend(df):
    """Plot candlestick chart with supertrend indicator"""
    logger.info("\n📊 Preparing to plot data with Supertrend...")
    if df is None or df.empty or 'SUPERT_10_2.0' not in df.columns:
        logger.error("❌ No data available for plotting")
        return
    
    logger.info("🖌 Creating Plotly figure...")
    fig = go.Figure()
    
    # Add candlestick trace
    logger.debug("🕯 Adding candlestick trace...")
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price"
    ))
    
    # Add Supertrend line
    logger.debug("📈 Adding Supertrend line...")
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[f"SUPERT_{SUPERTREND_LENGTH}_{SUPERTREND_FACTOR}"],
        mode="lines",
        name="Supertrend",
        line=dict(dash="dash", color="purple")
    ))
    
    # Add buy signals
    buy_signals = df[df['signal'] == 'buy']
    if not buy_signals.empty:
        logger.debug(f"🟢 Adding {len(buy_signals)} buy signals...")
        fig.add_trace(go.Scatter(
            x=buy_signals.index,
            y=buy_signals["low"] * 0.998,
            mode='markers',
            marker=dict(color='green', size=10, symbol='triangle-up'),
            name='Buy Signal'
        ))
    
    # Add sell signals
    sell_signals = df[df['signal'] == 'sell']
    if not sell_signals.empty:
        logger.debug(f"🔴 Adding {len(sell_signals)} sell signals...")
        fig.add_trace(go.Scatter(
            x=sell_signals.index,
            y=sell_signals["high"] * 1.002,
            mode='markers',
            marker=dict(color='red', size=10, symbol='triangle-down'),
            name='Sell Signal'
        ))
    
    # Calculate y-axis range with padding
    y_min = df["low"].min() * 0.99
    y_max = df["high"].max() * 1.01
    logger.debug(f"📏 Y-axis range: {y_min:.2f} to {y_max:.2f}")
    
    timeframe_minutes = CANDLE_SIZE_SECONDS.get(CANDLE_SIZE, 60) // 60
    fig.update_layout(
        title=f"Stock Data with Supertrend Indicator ({timeframe_minutes}-minute candles)",
        xaxis_title="Date/Time",
        yaxis_title="Price",
        yaxis=dict(range=[y_min, y_max])
    )
    
    # Remove non-trading hours and weekends
    logger.debug("⏰ Configuring x-axis range breaks...")
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),
            dict(bounds=[15.5, 9.25], pattern="hour")
        ]
    )
    
    logger.info("🖼 Displaying plot...")
    fig.show()

def execute_order(order_trading_symbol: str, 
                  order_symbol_token: str, 
                  order_quantity: int, 
                  transaction_type: str, 
                  order_exchange_segment: str = "NFO", # Default to NFO for options
                  product_type: str = "INTRADAY"):
    """Execute buy or sell order for a specific instrument."""
    global headers, logger, get_auth_token # Ensure get_auth_token is accessible

    logger.info(f"\n📢 Executing {transaction_type} order for {order_trading_symbol} (Token: {order_symbol_token}) "
                f"Qty: {order_quantity}, Exchange: {order_exchange_segment}, Product: {product_type}")
    
    current_api_headers = get_auth_token() # Get fresh/valid headers
    if not current_api_headers:
        logger.error(f"❌ Cannot place order for {order_trading_symbol}, authentication failed.")
        return False

    # The 'duration' was a global in your original file, defaulting to "DAY".
    # The 'producttype' was also a global, defaulting to "INTRADAY".
    # Using parameter for product_type, keeping duration as "DAY" as it's common.
    global duration # Assuming 'duration' is still a relevant global, though "DAY" is hardcoded below.
                   # If 'duration' needs to be flexible, it should be a parameter too.

    url = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder"
    #TODO: stoploss user input 
    payload = {
        "exchange": order_exchange_segment,
        "tradingsymbol": order_trading_symbol,
        "symboltoken": order_symbol_token,
        "quantity": order_quantity, # This is in units (lots * lotsize)
        "disclosedquantity": 0,
        "transactiontype": transaction_type, # "BUY" or "SELL"
        "duration": "DAY", # Hardcoded to DAY as it's typical for market orders
        "ordertype": "MARKET",
        "producttype": product_type, 
        "variety": "NORMAL"
    }

    print(payload)
    
    logger.debug(f"📡 Sending order with payload: {payload}")
    
    try:
        response = requests.post(url, json=payload, headers=current_api_headers, timeout=10)
        logger.debug(f"🔔 Received response with status code: {response.status_code}")
        print(response.json())
        response_data = response.json()
        logger.debug(f"📋 Order Response data: {response_data}")        
        if response_data.get("status") and response_data.get("data") and response_data["data"].get("orderid"):
            logger.info(f"✅ {transaction_type} order placed successfully! Order ID: {response_data['data']['orderid']}")
            # Set a success message when order is placed
            #global status_message
            #status_message = f"SUCCESS:{transaction_type}:{order_trading_symbol}"
            return True
        else:
            error_msg = response_data.get('message', response_data.get('remarks', 'Unknown error from API.'))
            logger.error(f"❌ Failed to place {transaction_type} order for {order_trading_symbol}: {error_msg}")
            return False
    except Exception as e:
        logger.error(f"⚠ Exception placing {transaction_type} order for {order_trading_symbol}: {str(e)}")
        logger.debug(traceback.format_exc())
        return False
    
def find_nearest_strike(current_price: float, option_type: str = None) -> tuple:
    """
    Find the nearest strike price and the option for that strike with the
    actual nearest *future* expiry date.
    """
    global option_data, logger, get_ist_now

    if option_data is None or option_data.empty:
        logger.error("❌ No options data available to find nearest strike.")
        return None

    try:
        # Log available expiries for debugging
        available_expiries = sorted(option_data['expiry'].unique())
        logger.info(f"Available option expiries: {available_expiries}")
        
        # Work on a copy for operations that might modify
        current_options_df_copy = option_data.copy()

        if 'strike' not in current_options_df_copy.columns:
            logger.error("❌ 'strike' column not found in options data.")
            return None
        
        # Perform scaling on the main option_data if that's the intended design
        # This ensures consistency if other parts of the code expect scaled strikes in global option_data
        if pd.api.types.is_numeric_dtype(option_data['strike']): # Check if already numeric
            pass
        else:
            option_data['strike'] = pd.to_numeric(option_data['strike'], errors='coerce')
            option_data.dropna(subset=['strike'], inplace=True)
        
        if option_data.empty: # Check global option_data after potential modification
             logger.error("❌ Global option_data is empty after strike column processing.")
             return None

        if not option_data['strike'].empty and option_data['strike'].max() > (current_price * 100):
            logger.info("ℹ️ (find_nearest_strike) Strike prices seem to be in paisa. Converting global option_data strikes to rupees.")
            option_data.loc[:, 'strike'] = option_data['strike'] / 100
        
        # Use the corrected global option_data for finding strikes
        strikes = sorted(option_data['strike'].dropna().unique())
        
        if not strikes:
            logger.error("❌ No valid unique strikes found in options data after processing.")
            return None
            
        nearest_strike_value = min(strikes, key=lambda x: abs(float(x) - current_price))
        logger.info(f"🎯 (find_nearest_strike) Selected numerically nearest strike (in rupees): {nearest_strike_value:.2f}")
        
        if option_type:
            required_cols_check = ['symbol', 'token', 'lotsize', 'expiry']
            if not all(col in option_data.columns for col in required_cols_check):
                missing = [col for col in required_cols_check if col not in option_data.columns]
                logger.error(f"❌ Missing required columns in global option_data: {missing}")
                return None

            # Filter by strike and option type from the (potentially scaled) global option_data
            options_for_strike_type = option_data[
                (option_data['strike'] == nearest_strike_value) & 
                (option_data['symbol'].str.endswith(option_type.upper()))
            ].copy() # Use .copy() for safe modifications

            if options_for_strike_type.empty:
                logger.warning(f"⚠️ (find_nearest_strike) No {option_type.upper()} options found for strike {nearest_strike_value:.2f}.")
                return None

            # Now, find the one with the nearest *future* expiry from this subset
            try:
                options_for_strike_type.loc[:, 'expiry_date_obj'] = pd.to_datetime(
                    options_for_strike_type['expiry'], format='%d%b%Y', errors='coerce'
                ).dt.date
                options_for_strike_type.dropna(subset=['expiry_date_obj'], inplace=True)

                if options_for_strike_type.empty:
                    logger.error(f"❌ No valid expiry dates after conversion for {option_type.upper()} at strike {nearest_strike_value:.2f}.")
                    return None
            except Exception as e:
                logger.error(f"❌ Error converting expiry dates for {option_type.upper()} at strike {nearest_strike_value:.2f}: {e}")
                logger.debug(traceback.format_exc())
                return None
            
            current_date_ist = get_ist_now().date()
            future_options = options_for_strike_type[options_for_strike_type['expiry_date_obj'] >= current_date_ist].copy()

            if future_options.empty:
                logger.warning(f"⏳ (find_nearest_strike) No *future* {option_type.upper()} options for strike {nearest_strike_value:.2f} on or after {current_date_ist.strftime('%Y-%m-%d')}.")
                return None
                
            # Find the minimum future expiry date (this is the nearest actual future expiry)
            nearest_actual_expiry_date = future_options['expiry_date_obj'].min()
            
            # Select the option(s) for this specific nearest future expiry date
            final_selected_option_df = future_options[future_options['expiry_date_obj'] == nearest_actual_expiry_date]
            
            if final_selected_option_df.empty: 
                logger.error(f"Logic error: No options found for nearest future expiry {nearest_actual_expiry_date.strftime('%Y-%m-%d')}, strike {nearest_strike_value:.2f}, type {option_type.upper()}")
                return None
                
            selected_option_row = final_selected_option_df.iloc[0] # Pick the first (should be unique enough for a given day and type)
            
            logger.info(f"✅ (find_nearest_strike - Corrected Expiry) Found {option_type.upper()} option: Symbol - {selected_option_row['symbol']}, Token - {selected_option_row['token']}, Lotsize: {selected_option_row['lotsize']} for strike {nearest_strike_value:.2f} with actual nearest future expiry {nearest_actual_expiry_date.strftime('%Y-%m-%d')}")
            return (nearest_strike_value, selected_option_row['symbol'], str(selected_option_row['token']), int(selected_option_row['lotsize']))
        else:
            # This path is taken by apply_trading_strategy initially.
            # It's okay for it to just return the strike value if no option_type is given.
            logger.warning("⚠️ find_nearest_strike called without specific option_type. Returning strike value and None for other details.")
            return (nearest_strike_value, None, None, None)

    except Exception as e:
        logger.error(f"❌ Error in find_nearest_strike (Corrected Expiry): {str(e)}")
        logger.debug(traceback.format_exc())
        return None
                
def find_options_at_strike_with_nearest_expiry(target_strike_price: float,
                                             current_option_data: pd.DataFrame) -> tuple:
    """
    Finds CE and PE options for a given strike price with the nearest future expiry date.

    Args:
        target_strike_price (float): The specific strike price to look for (in rupees).
        current_option_data (pd.DataFrame): The DataFrame containing options data.
                                         Expected to have 'strike', 'expiry', 'symbol', 'token' columns.
                                         The 'strike' column should already be in rupees.

    Returns:
        tuple: (ce_option_details, pe_option_details)
               Each _details is a dictionary with keys:
               {'symbol', 'token', 'expiry_date', 'strike_price', 'option_type', 'original_expiry_str'}
               or None if not found.
    """
    global logger # Assuming logger is globally available as in your script

    logger.info(f"🔍 Finding options with nearest expiry for strike: {target_strike_price:.2f}") #

    if current_option_data is None or current_option_data.empty:
        logger.error("❌ Options data is not available for finding nearest expiry.") #
        return None, None

    required_columns = ['strike', 'expiry', 'symbol', 'token']
    if not all(col in current_option_data.columns for col in required_columns):
        logger.error(f"❌ Options data is missing one or more required columns: {required_columns}.") #
        return None, None

    # Filter for the target strike price
    options_at_strike = current_option_data[current_option_data['strike'] == target_strike_price].copy()

    if options_at_strike.empty:
        logger.warning(f"⚠️ No options found in the provided data for strike price: {target_strike_price:.2f}") #
        return None, None

    # Convert 'expiry' column to datetime.date objects for comparison
    # The format from OpenAPIScripMaster.json for expiry is typically 'DDMMMYYYY' (e.g., '23MAY2024')
    try:
        # Store original expiry string before conversion for potential use
        options_at_strike.loc[:, 'original_expiry_str'] = options_at_strike['expiry']
        options_at_strike.loc[:, 'expiry_date_obj'] = pd.to_datetime(options_at_strike['expiry'],
                                                                  format='%d%b%Y',
                                                                  errors='coerce').dt.date
        options_at_strike.dropna(subset=['expiry_date_obj'], inplace=True) # Remove rows where conversion failed

        if options_at_strike.empty:
            logger.error(f"❌ No valid expiry dates found for strike {target_strike_price:.2f} after date conversion.") #
            return None, None
    except Exception as e:
        logger.error(f"❌ Error converting expiry strings to dates for strike {target_strike_price:.2f}: {e}") #
        logger.debug(traceback.format_exc()) #
        return None, None

    current_date_ist = get_ist_now().date() # Get current date in IST

    # Filter for expiries that are on or after the current date
    future_expiries_df = options_at_strike[options_at_strike['expiry_date_obj'] >= current_date_ist].copy()

    if future_expiries_df.empty:
        logger.warning(f"⏳ No future expiry dates found for strike {target_strike_price:.2f} on or after {current_date_ist.strftime('%Y-%m-%d')}.") #
        return None, None

    # Find the minimum future expiry date (this is the nearest future expiry)
    nearest_expiry_date_obj = future_expiries_df['expiry_date_obj'].min()
    logger.info(f"🎯 Nearest future expiry date for strike {target_strike_price:.2f} is: {nearest_expiry_date_obj.strftime('%Y-%m-%d')}") #

    # Get CE and PE options for this strike and nearest expiry date
    final_options_for_nearest_expiry = future_expiries_df[future_expiries_df['expiry_date_obj'] == nearest_expiry_date_obj]

    ce_option_details = None
    pe_option_details = None

    ce_row = final_options_for_nearest_expiry[final_options_for_nearest_expiry['symbol'].str.endswith('CE')]
    if not ce_row.empty:
        ce = ce_row.iloc[0]
        ce_option_details = {
            "symbol": ce['symbol'],
            "token": str(ce['token']), # Ensure token is string
            "expiry_date": nearest_expiry_date_obj.strftime('%Y-%m-%d'),
            "original_expiry_str": ce['original_expiry_str'],
            "strike_price": target_strike_price,
            "option_type": "CE"
        }
        logger.info(f"✅ Selected CE Option: {ce_option_details['symbol']} (Token: {ce_option_details['token']}) for expiry {ce_option_details['expiry_date']}") #

    pe_row = final_options_for_nearest_expiry[final_options_for_nearest_expiry['symbol'].str.endswith('PE')]
    if not pe_row.empty:
        pe = pe_row.iloc[0]
        pe_option_details = {
            "symbol": pe['symbol'],
            "token": str(pe['token']), # Ensure token is string
            "expiry_date": nearest_expiry_date_obj.strftime('%Y-%m-%d'),
            "original_expiry_str": pe['original_expiry_str'],
            "strike_price": target_strike_price,
            "option_type": "PE"
        }
        logger.info(f"✅ Selected PE Option: {pe_option_details['symbol']} (Token: {pe_option_details['token']}) for expiry {pe_option_details['expiry_date']}") #

    if not ce_option_details and not pe_option_details:
        logger.warning(f"⚠️ Could not find specific CE or PE options for strike {target_strike_price:.2f} and expiry {nearest_expiry_date_obj.strftime('%Y-%m-%d')}.") #
        return None, None

    return ce_option_details, pe_option_details

def execute_order_basic(trading_symbol, quantity, transaction_type):
    """Execute buy or sell order"""
    global headers
    
    print(f"\n📢 Executing {transaction_type} order for {trading_symbol} (Qty: {quantity})...")
    url = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder"
    
    payload = {
        "exchange": exchange,
        "tradingsymbol": trading_symbol,
        "symboltoken": symbol_token,
        "quantity": quantity,
        "disclosedquantity": 0,
        "transactiontype": transaction_type,
        "duration": duration,
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "variety": "NORMAL"
    }
    
    print(f"📡 Sending order with payload: {payload}")
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"🔔 Received response with status code: {response.status_code}")
        
        response_data = response.json()
        print(f"📋 Response data: {response_data}")
        if response_data.get("status"):
            print(f"✅ {transaction_type} order placed successfully! Order ID: {response_data.get('data', {}).get('orderid')}")
            # Set a success message when order is placed
            #global status_message
            #status_message = f"SUCCESS:{transaction_type}:{trading_symbol}"
            return True
        else:
            print(f"❌ Failed to place {transaction_type} order: {response_data.get('message')}")
            return False
    except Exception as e:
        print(f"⚠ Error placing {transaction_type} order: {str(e)}")
        return False
    
def apply_trading_strategy(df, trading_symbol_of_underlying, quantity_of_underlying): # Renamed params for clarity
    """Apply trading strategy based on supertrend signals.
    This version selects appropriate option contracts but defers option execution logic.
    """
    global active_position, entry_price, option_data #
    global trade_history, total_profit_loss, current_trade_entry_price, current_trade_entry_time #
    global trade_count, winning_trades, losing_trades #
    
    logger.info("\n🧠 Applying trading strategy (with option selection)...") #
    
    if df is None or df.empty or 'signal' not in df.columns:
        logger.error("❌ No data or signal column available for strategy application.") #
        return
    
    latest_candle = df.iloc[-1] #
    current_price_of_underlying = latest_candle['close'] #
    current_signal = latest_candle['signal'] #
    signal_changed = latest_candle.get('signal_change', False) #

    logger.info(f"📈 Underlying ({trading_symbol_of_underlying}) Current Price: {current_price_of_underlying:.2f}") #
    logger.info(f"🕯️ Underlying Candle Time: {latest_candle.name}, Signal: {current_signal}, Changed: {signal_changed}") #
    logger.info(f"📊 Underlying Price Data - O:{latest_candle['open']:.2f} H:{latest_candle['high']:.2f} L:{latest_candle['low']:.2f} C:{latest_candle['close']:.2f}") #

    # --- Option Selection Logic ---
    selected_option_to_consider = None
    
    # Step 1: Determine the numerically nearest strike from the underlying's price.
    # find_nearest_strike also processes the global option_data (e.g., for rupee conversion of strikes).
    # raw_option_details_for_strike_value = find_nearest_strike(current_price_of_underlying) #

    # if not raw_option_details_for_strike_value:
    #     logger.error("❌ Could not determine a nearest strike value from underlying price. Cannot select option.") #
    # else:
    #     nearest_strike_val = raw_option_details_for_strike_value[0] # The strike price value itself
    #     logger.info(f"🎯 Identified numerically nearest strike value for options: {nearest_strike_val:.2f}") #

    # Step 2: Find the CE and PE options at this strike with the actual nearest *future* expiry.
    # Pass the global option_data, which find_nearest_strike might have processed.
    # ce_details, pe_details = find_options_at_strike_with_nearest_expiry(nearest_strike_val, option_data) #

    # if not ce_details and not pe_details:
    #     logger.warning(f"⚠️ Could not find any suitable CE/PE options for strike {nearest_strike_val:.2f} with nearest future expiry.") #
    # else:
    #     # Step 3: Select option based on trading signal for the underlying.
    #     if current_signal == 'buy': # Supertrend BUY signal for underlying -> Bullish on underlying.
    #         if ce_details:
    #             selected_option_to_consider = ce_details
    #             logger.info(f"📈 Underlying Supertrend BUY. Considered CALL option: {selected_option_to_consider['symbol']} (Expiry: {selected_option_to_consider['expiry_date']})") #
    #         else:
    #             logger.warning("⚠️ Underlying Supertrend BUY, but no CE option details found for nearest expiry.") #
    #     elif current_signal == 'sell': # Supertrend SELL signal for underlying -> Bearish on underlying.
    #         if pe_details:
    #             selected_option_to_consider = pe_details
    #             logger.info(f"📉 Underlying Supertrend SELL. Considered PUT option: {selected_option_to_consider['symbol']} (Expiry: {selected_option_to_consider['expiry_date']})") #
    #         else:
    #             logger.warning("⚠️ Underlying Supertrend SELL, but no PE option details found for nearest expiry.") #
    #     else:
    #         logger.info(f"ℹ️ No actionable trading signal ('{current_signal}') for option selection.") #
# --- End of Option Selection Logic ---

    # --- Existing Position Management Logic (Operates on Underlying) ---
    # IMPORTANT: The following logic (open_position, close_position) and its call
    # to execute_order will still operate on the UNDERLYING security as per current script structure,
    # using 'trading_symbol_of_underlying' and 'quantity_of_underlying'.
    # Changes to trade the *selected_option_to_consider* would require modifying
    # open_position, close_position, and execute_order.

    if signal_changed:
        if stock_name in ['SENSEX', 'NIFTY', 'BANKNIFTY']: 
            logger.info(f"Doing Index Trade")
            logger.info(f"🔁 Signal changed for underlying '{trading_symbol_of_underlying}'.") #
            # Close existing position if there is one (for the underlying)
            if active_position:
                # Passing trading_symbol_of_underlying and quantity_of_underlying
                close_position(latest_candle, trading_symbol_of_underlying, quantity_of_underlying) #
            
            # Open new position based on the signal (for the underlying)
            # We have an option in mind, but action is on underlying for now
            # Log that we're proceeding with underlying trade logic based on the considered option
            #if selected_option_to_consider: 
                #logger.info(f"ℹ️ Based on option consideration ({selected_option_to_consider['option_type']} {selected_option_to_consider['symbol']}), proceeding with underlying trade logic.")
            # Passing trading_symbol_of_underlying and quantity_of_underlying
            open_position(latest_candle, current_signal, trading_symbol_of_underlying, quantity_of_underlying) #
        else:
            if instrument_type == '' and exchange in ['NSE','BSE']:
                logger.info(f"Doing Equity Trade") 
                logger.info(f"🔁 Signal changed for underlying '{trading_symbol_of_underlying}'.")
                if active_position:
                    close_position_basic(latest_candle, trading_symbol_of_underlying, quantity_of_underlying)
                else:
                    if current_signal == 'buy':
                        logger.info(f"📈 Opening BUY position for underlying '{trading_symbol_of_underlying}' with quantity {quantity_of_underlying}.")
                        open_position_basic(latest_candle, current_signal, trading_symbol_of_underlying, quantity_of_underlying)
                    else:   
                        logger.info(f"ℹ️ No action taken for current signal '{current_signal}' on underlying '{trading_symbol_of_underlying}'.")
            else:
                logger.info(f"Doing Basic Trade") 
                logger.info(f"🔁 Signal changed for underlying '{trading_symbol_of_underlying}'.")
                # Close existing position if there is one (for the underlying)
                if active_position:
                    close_position_basic(latest_candle, trading_symbol_of_underlying, quantity_of_underlying)
                # Open new position based on the signal
                open_position_basic(latest_candle,current_signal,trading_symbol_of_underlying,quantity_of_underlying)
    else:
            logger.info(f"↔️ Signal for underlying '{trading_symbol_of_underlying}' has not changed. No new action on underlying position.") #

def close_position_basic(latest_candle, trading_symbol, quantity):
    """Close existing position"""
    global active_position, entry_price
    global trade_history, total_profit_loss, current_trade_entry_price, current_trade_entry_time
    global trade_count, winning_trades, losing_trades
    
    exit_price = latest_candle['close']
    
    if active_position == "long":
        trade_profit = (exit_price - entry_price) * quantity
        trade_profit_pct = (exit_price / entry_price - 1) * 100
        order_type = "SELL"
        position_type = "LONG"
        print(f"📉 Closing LONG position (Entry: {entry_price}, Exit: {exit_price})")
    else:  # short position
        trade_profit = (entry_price - exit_price) * quantity
        trade_profit_pct = (entry_price / exit_price - 1) * 100
        order_type = "BUY"
        position_type = "SHORT"
        print(f"📈 Closing SHORT position (Entry: {entry_price}, Exit: {exit_price})")
    
    total_profit_loss += trade_profit
    trade_count += 1
    
    if trade_profit > 0:
        winning_trades += 1
        result_emoji = "✅"
    else:
        losing_trades += 1
        result_emoji = "❌"
    
    trade_info = {
        "type": position_type,
        "entry_time": current_trade_entry_time,
        "entry_price": entry_price,
        "exit_time": latest_candle.name,
        "exit_price": exit_price,
        "quantity": quantity,
        "profit_loss": trade_profit,
        "profit_loss_pct": trade_profit_pct
    }
    trade_history.append(trade_info)
    
    print(f"🔄 Closing {active_position} position at {exit_price} at {latest_candle.name}")
    print(f"{result_emoji} P&L: ₹{trade_profit:.2f} ({trade_profit_pct:.2f}%)")
    print(f"💰 Total P&L: ₹{total_profit_loss:.2f} | Trades: {trade_count} | Win/Loss: {winning_trades}/{losing_trades}")
    
    execute_order_basic(trading_symbol, quantity, order_type)
    active_position = None
    print("🔄 Position closed and reset")

def open_position_basic(latest_candle, current_signal, trading_symbol, quantity):
    """Open new position based on signal"""
    global active_position, entry_price
    global current_trade_entry_price, current_trade_entry_time
    
    entry_price = latest_candle['close']
    current_trade_entry_price = entry_price
    current_trade_entry_time = latest_candle.name
    
    if current_signal == 'buy':
        print(f"📈 Opening BUY position at {entry_price}")
        execute_order_basic(trading_symbol, quantity, "BUY")
        active_position = "long"
    elif current_signal == 'sell':
        print(f"📉 Opening SELL position at {entry_price}")
        execute_order_basic(trading_symbol, quantity, "SELL")
        active_position = "short"
    
    print(f"🆕 New {active_position} position opened at {entry_price}")

def close_position(latest_candle, underlying_symbol_arg, num_lots_arg_on_call): # num_lots_arg_on_call might not be used if active_pos has all info
    """Close existing active option position."""
    global active_position, entry_price, current_trade_entry_time, trade_history, total_profit_loss, trade_count, winning_trades, losing_trades, logger, execute_order
    
    if not active_position or not isinstance(active_position, dict) or 'symbol' not in active_position: 
        logger.info("ℹ️ No active option position to close or active_position is not in expected option format.")
        return

    logger.info(f"--- Attempting to Close Option Position: {active_position.get('symbol')} ---")
    
    # These details are from the active option position
    option_details_from_active_pos = active_position 
    opt_symbol = option_details_from_active_pos['symbol']
    opt_token = option_details_from_active_pos['token']
    opt_lotsize = option_details_from_active_pos['lotsize']
    opt_num_lots_traded = option_details_from_active_pos['num_lots'] # Number of lots that were opened
    
    # Retrieve the placeholder entry price from the global variable set during open_position
    opt_entry_price_placeholder = entry_price 

    quantity_in_units = opt_num_lots_traded * opt_lotsize
    
    # To close a BOUGHT option, we SELL it
    transaction_type_for_exit = "SELL"

    logger.info(f"📉 Closing position for option {opt_symbol} by {transaction_type_for_exit}ing (Units: {quantity_in_units})")
    #TODO: Get the actual exit price of the option from the market
    # ! Placeholder for option's exit price.
    placeholder_option_exit_price = 0.0 
    logger.warning(f"❗ Using placeholder_option_exit_price = {placeholder_option_exit_price}. Actual fill price of option needed for P&L.")
    logger.warning(f"❗ P&L calculation is based on placeholder entry ({opt_entry_price_placeholder if opt_entry_price_placeholder is not None else 'N/A'}) and exit ({placeholder_option_exit_price}) prices.")

    # Ensure opt_entry_price_placeholder is a number for calculation
    if opt_entry_price_placeholder is None: opt_entry_price_placeholder = 0.0

    trade_profit = (placeholder_option_exit_price - opt_entry_price_placeholder) * quantity_in_units
    
    total_profit_loss += trade_profit
    trade_count += 1
    
    result_emoji = "✅ (Placeholder PNL)" if trade_profit > 0 else "❌ (Placeholder PNL)"
    if trade_profit > 0:
        winning_trades += 1
    else:
        losing_trades += 1
    
    # Use global current_trade_entry_time which was set when position was opened
    trade_info = {
        "type": f"{option_details_from_active_pos.get('type','OPTION')}_BUY_THEN_SELL", 
        "entry_time": current_trade_entry_time if current_trade_entry_time else option_details_from_active_pos.get('entry_time', latest_candle.name),
        "entry_price": opt_entry_price_placeholder, 
        "exit_time": latest_candle.name,
        "exit_price": placeholder_option_exit_price, 
        "quantity": quantity_in_units, 
        "profit_loss": trade_profit,
        "profit_loss_pct": 0.0, # Cannot calculate accurately without real prices
        "option_symbol": opt_symbol
    }
    trade_history.append(trade_info)
    
    logger.info(f"🔄 Closing option {opt_symbol}. Underlying exit ref price from candle: {latest_candle['close']:.2f} at {latest_candle.name}")
    logger.info(f"{result_emoji} P&L for option trade: ₹{trade_profit:.2f}")
    logger.info(f"💰 Total P&L: ₹{total_profit_loss:.2f} | Trades: {trade_count} | Win/Loss: {winning_trades}/{losing_trades}")
    
    if stock_name in [ 'NIFTY', 'BANKNIFTY']:
        exch_seg = "NFO"
    else:
        exch_seg = "BFO"

    success = execute_order(
        order_trading_symbol=opt_symbol,
        order_symbol_token=opt_token,
        order_quantity=quantity_in_units,
        transaction_type=transaction_type_for_exit, # SELL
        order_exchange_segment= exch_seg,
        product_type="INTRADAY"
    )
    
    if success:
        logger.info(f"✅ SELL order for option {opt_symbol} placed to close position.")
    else:
        logger.error(f"❌ Failed to place SELL order to close option {opt_symbol}. Manual intervention may be required.")

    active_position = None
    entry_price = None 
    current_trade_entry_time = None 
    logger.info("🔄 Option position details cleared and reset.")
    
def open_position(latest_candle, current_signal, underlying_symbol_arg, num_lots_arg):
    """Open new option position based on underlying's signal."""
    global active_position, entry_price, current_trade_entry_time, logger, option_data, find_nearest_strike, execute_order
    
    logger.info(f"--- Attempting to Open Option Position based on Underlying Signal: {current_signal} ---")
    current_price_of_underlying = latest_candle['close']
    option_to_trade_details_dict = None # To avoid confusion with global active_position
    selected_option_type = None

    if current_signal == 'buy': # Bullish on underlying, so buy Call
        selected_option_type = 'CE'
        logger.info(f"Underlying signal is BUY for {underlying_symbol_arg}, attempting to select a CALL option.")
    elif current_signal == 'sell': # Bearish on underlying, so buy Put
        selected_option_type = 'PE'
        logger.info(f"Underlying signal is SELL for {underlying_symbol_arg}, attempting to select a PUT option.")
    else:
        logger.warning(f"⚠️ Unknown signal '{current_signal}' for underlying {underlying_symbol_arg}. Cannot determine option type.")
        return

    # Find the option to trade
    # find_nearest_strike now returns: (strike, opt_symbol, opt_token, opt_lotsize)
    # It uses and potentially modifies global option_data for scaling.
    option_info_tuple = find_nearest_strike(current_price_of_underlying, option_type=selected_option_type)

    if option_info_tuple and len(option_info_tuple) == 4: # Check for correct tuple length
        _strike, opt_symbol, opt_token, opt_lotsize = option_info_tuple
        if opt_symbol and opt_token and opt_lotsize and opt_lotsize > 0:
            option_to_trade_details_dict = {
                "type": selected_option_type, # CE or PE
                "symbol": opt_symbol,
                "token": opt_token,
                "lotsize": opt_lotsize,
                "num_lots": num_lots_arg, 
                "entry_price_placeholder": 0.0, # ! Placeholder for option's actual entry price
                "entry_time": latest_candle.name # Time of the underlying's signal candle
            }
            logger.info(f"Selected option for {current_signal} signal: {opt_symbol}, Lotsize: {opt_lotsize}, Num Lots to trade: {num_lots_arg}")
        else:
            logger.error(f"❌ Could not get valid details (symbol, token, or lotsize) for {selected_option_type} option at strike {_strike}.")
            return
    else:
        logger.error(f"❌ Failed to find a suitable {selected_option_type} option for underlying price {current_price_of_underlying:.2f}.")
        return

    # Proceed to execute order for the selected option
    quantity_in_units = option_to_trade_details_dict['num_lots'] * option_to_trade_details_dict['lotsize']
    
    logger.info(f"📈 Opening BUY position for {option_to_trade_details_dict['type']} option: {option_to_trade_details_dict['symbol']} (Units: {quantity_in_units})")
    logger.warning("❗ Option entry price will be a placeholder (0.0). Actual fill price needed for correct P&L.")

    if stock_name in [ 'NIFTY', 'BANKNIFTY']:
        exch_seg = "NFO"
    else:
        exch_seg = "BFO"

    success = execute_order(
        order_trading_symbol=option_to_trade_details_dict['symbol'],
        order_symbol_token=option_to_trade_details_dict['token'],
        order_quantity=quantity_in_units,
        transaction_type="BUY", # We are buying the option (CE or PE)
        order_exchange_segment=exch_seg, 
        product_type="INTRADAY" 
    )
    #TODO : See P&L
    if success:
        active_position = option_to_trade_details_dict # Store option details in global active_position
        entry_price = option_to_trade_details_dict['entry_price_placeholder'] # Global entry_price for option (placeholder)
        current_trade_entry_time = option_to_trade_details_dict['entry_time'] # Global current_trade_entry_time
        logger.info(f"✅ BUY order for option {active_position['symbol']} placed. Position marked active (with placeholder entry price).")
    else:
        logger.error(f"❌ Failed to execute BUY order for option {option_to_trade_details_dict['symbol']}.")

def save_trade_history():
    """Log trade history summary without saving to CSV (for cloud environment)"""
    global trade_history
    
    logger.info("\n📊 Generating trade history summary...")
    if not trade_history:
        logger.info("📭 No trades to summarize")
        return
        
    try:
        df = pd.DataFrame(trade_history)
        logger.info(f"✅ Trade summary: {len(trade_history)} trades completed")
        
        # Log trade stats without saving to file
        if len(df) > 0:
            profit_trades = df[df['profit_loss'] > 0]
            loss_trades = df[df['profit_loss'] <= 0]
            
            total_profit = df['profit_loss'].sum()
            avg_profit_per_trade = df['profit_loss'].mean()
            win_rate = len(profit_trades) / len(df) * 100 if len(df) > 0 else 0
            
            logger.info(f"💰 Total P&L: ₹{total_profit:.2f}")
            logger.info(f"📈 Win rate: {win_rate:.2f}% ({len(profit_trades)}/{len(df)})")
            logger.info(f"⚖️ Avg P&L per trade: ₹{avg_profit_per_trade:.2f}")
            
            # Show recent trades
            recent_trades = df.tail(3)
            logger.info("🔄 Recent trades:")
            for idx, trade in recent_trades.iterrows():
                logger.info(f"  {trade['type']} | Entry: ₹{trade['entry_price']:.2f} | Exit: ₹{trade['exit_price']:.2f} | P&L: ₹{trade['profit_loss']:.2f} ({trade['profit_loss_pct']:.2f}%)")
                
    except Exception as e:
        logger.error(f"❌ Error generating trade history summary: {str(e)}")
        logger.debug(traceback.format_exc())

def is_market_open():
    """Check if market is currently open"""
    now = get_ist_now()
    current_time = now.time()
    
    logger.debug(f"\n🕒 Checking market hours - Current time: {current_time}")
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday or Sunday
        logger.info("📅 Weekend detected - Market closed")
        return False
    
    # Check market hours
    market_start = datetime.time(9, 15)
    market_end = datetime.time(15, 30)
    
    market_status = market_start <= current_time <= market_end
    logger.info(f"🏛 Market status: {'OPEN' if market_status else 'CLOSED'}")
    return market_status

# Function to display DataFrames with Supertrend information in a user-friendly format
def display_supertrend_dataframe(df, timestamp=None):
    """Display a summary of the DataFrame with Supertrend information"""
    global SUPERTREND_LENGTH, SUPERTREND_FACTOR
    
    if timestamp:
        logger.info(f"\n📊 DataFrame Summary at {timestamp}:")
    else:
        logger.info(f"\n📊 DataFrame Summary:")
    
    # Show basic DataFrame info
    logger.info(f"   Total rows: {len(df)}")
    logger.info(f"   Date range: {df.index.min()} to {df.index.max()}")
    
    # Display the latest few rows with key columns
    # Get the actual Supertrend column name based on current parameters
    supertrend_col = f"SUPERT_{SUPERTREND_LENGTH}_{SUPERTREND_FACTOR}"
    if supertrend_col in df.columns and 'signal' in df.columns:
        key_columns = ['open', 'high', 'low', 'close', supertrend_col, 'signal', 'signal_change']
        logger.info("\n   Latest data with Supertrend indicators:")
        logger.debug(df[key_columns].tail().to_string())
        
        # Signal stats
        buy_signals = df[df['signal'] == 'buy'].shape[0]
        sell_signals = df[df['signal'] == 'sell'].shape[0]
        changes = df[df['signal_change'] == True].shape[0]
        
        logger.info(f"\n   Signal distribution - Buy: {buy_signals}, Sell: {sell_signals}, Changes: {changes}")
        
        # Show the difference between price and Supertrend
        latest_row = df.iloc[-1]
        price_supertrend_diff = latest_row['close'] - latest_row['SUPERT_10_2.0']
        cross_potential = abs(price_supertrend_diff) / latest_row['close'] * 100
        
        logger.info(f"   Latest close price: {latest_row['close']:.2f}")
        logger.info(f"   Latest Supertrend value: {latest_row['SUPERT_10_2.0']:.2f}")
        logger.info(f"   Difference: {price_supertrend_diff:.2f} ({cross_potential:.2f}% away from signal change)")
    else:
        logger.warning("   Supertrend indicators not available in DataFrame")

def get_trade_history():
    """Return the current trade history"""
    global trade_history
    return trade_history

def clean_up_resources():
    """Clean up resources and gracefully exit"""
    global active_position, trading_symbol, quantity, symbol_token
    
    logger.info("\n🧹 Cleaning up resources...")
    
    # Close any open positions
    if active_position:
        logger.warning(f"🚨 Found active {active_position} position during cleanup")
        # Create a dummy candle at current market price to close the position
        try:
            url = "https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/"
            payload = {"mode": "LTP", "exchangeTokens": {exchange: [symbol_token]}}
            response = requests.post(url, json=payload, headers=headers)
            
            if response.ok and "data" in response.json():
                ltp_data = response.json()["data"].get("fetched", [])
                if ltp_data:
                    current_price = float(ltp_data[0].get("ltp", 0))
                    logger.info(f"📊 Current price: {current_price}")
                    
                    # Create dummy candle
                    dummy_candle = pd.Series({
                        'open': current_price,
                        'high': current_price,
                        'low': current_price,
                        'close': current_price,
                        'volume': 0
                    }, name=pd.Timestamp.now())
                    
                    # Force close the position
                    close_position(dummy_candle, trading_symbol, quantity)
                else:
                    logger.error("❌ No price data available for cleanup")
            else:
                logger.error("❌ Failed to get price data for cleanup")
        except Exception as e:
            logger.error(f"⚠ Error during position cleanup: {str(e)}")
            logger.debug(traceback.format_exc())
    
    # Generate trade summary (no file saving)
    save_trade_history()
    
    # Logout from Angel One
    try:
        logout_from_angel_one()
    except Exception as e:
        logger.error(f"⚠ Error during logout: {str(e)}")
        logger.debug(traceback.format_exc())
    
    logger.info("🏁 Cleanup completed")

# Modified main function to use our enhanced candle fetching
def main(api_token=None, stop_event=None):
    #global status_message
    if not login_to_angel_one(api_token):
        #status_message = "Login failed. Please press 'Stop Trading', enter the correct API key, and try again."
        logger.error("❌ Login failed. Exiting...")

        return False

    timeframe_seconds = CANDLE_SIZE_SECONDS.get(CANDLE_SIZE, 60)
    timeframe_minutes = timeframe_seconds // 60
    logger.info(f"🕰 Using {timeframe_minutes}-minute candles ({CANDLE_SIZE})")

    # Get initial historical candles
    historical_df = fetch_historical_stock_data(symbol_token, exchange)
    
    # Initialize an empty DataFrame if historical data is not available
    if historical_df is None:
        logger.warning("⚠ No historical data available. Starting with empty dataset.")
        columns = ["open", "high", "low", "close", "volume"]
        historical_df = pd.DataFrame(columns=columns)
        historical_df.index.name = "date"
    
    # Convert DataFrame to list of dictionaries for easier manipulation
    candles_list = []
    if not historical_df.empty:
        historical_df = historical_df.reset_index()
        # Ensure all datetime objects are timezone-naive
        historical_df['date'] = pd.to_datetime(historical_df['date']).dt.tz_localize(None)
        candles_list = historical_df.to_dict('records')
        logger.info(f"✅ Loaded {len(candles_list)} historical candles")

    # Setup the schedule for candle fetching
    last_fetched_candle_time = None
    fetch_time = get_ist_now().replace(second=0, microsecond=0)

    # Main trading loop 
    try:
        while stop_event is None or not stop_event.is_set():
            now = get_ist_now()
            current_minute = now.replace(second=0, microsecond=0)
            
            # Calculate if we're at a candle close time
            is_candle_close_time = False
            if timeframe_minutes == 1:
                # For 1-minute candles, check if we're at the start of a new minute
                is_candle_close_time = now.second == 0
            else:
                # For 5-minute candles, check if we're at :00, :05, :10, etc.
                is_candle_close_time = (now.minute % timeframe_minutes == 0) and now.second == 0
            
            # Calculate the next fetch time based on candle duration
            minutes_since_last_fetch = (current_minute - fetch_time).total_seconds() / 60
            
            if is_candle_close_time:
                # Calculate the start time of the candle we want to fetch
                # We want to fetch the PREVIOUS candle, not the current one
                candle_start_minute = current_minute - timedelta(minutes=timeframe_minutes)
                
                # Only fetch if we haven't fetched this candle before
                if last_fetched_candle_time is None or candle_start_minute > last_fetched_candle_time:
                    logger.info(f"\n⏰ It's {now.strftime('%H:%M:%S')} - Time to fetch {timeframe_minutes}-minute candle")
                    
                    # Fetch candle with retry mechanism
                    new_candle = fetch_candle(
                        candle_start_minute, 
                        symbol_token, 
                        exchange, 
                        "REGULAR",
                        max_retries=5,  # Will try 5 times
                        retry_delay=1   # 1 second between retries
                    )
                    
                    if new_candle:
                        logger.info(f"✅ Fetched {timeframe_minutes}-minute candle for {candle_start_minute.strftime('%H:%M')}!")
                        
                        # Ensure new_candle date is timezone-naive
                        if hasattr(new_candle['date'], 'tz_localize'):
                            new_candle['date'] = new_candle['date'].tz_localize(None)
                        
                        # Check if this timestamp already exists
                        exists = False
                        for i, existing_candle in enumerate(candles_list):
                            if pd.to_datetime(existing_candle['date']).replace(tzinfo=None) == new_candle['date'].replace(tzinfo=None):
                                candles_list[i] = new_candle  # Replace with new data
                                exists = True
                                break
                        
                        if not exists:
                            candles_list.append(new_candle)
                        
                        # Sort candles by date and keep only the most recent 100
                        candles_list = sorted(candles_list, key=lambda x: pd.to_datetime(x['date']).replace(tzinfo=None))
                        if len(candles_list) > 100:
                            candles_list = candles_list[-100:]
                        
                        # Convert list back to DataFrame
                        df = pd.DataFrame(candles_list)
                        df = df.set_index('date')
                        
                        logger.debug(f"📊 Updated DataFrame: {len(df)} candles, spanning {df.index.min()} to {df.index.max()}")
                        
                        # Calculate Supertrend
                        df_with_supertrend = calculate_supertrend(df)
                        
                        supertrend_col = f"SUPERT_{SUPERTREND_LENGTH}_{SUPERTREND_FACTOR}"
                        if df_with_supertrend is not None and supertrend_col in df_with_supertrend.columns:
                            logger.info("✅ Supertrend calculation successful!")
                            latest = df_with_supertrend.iloc[-1]
                            logger.info(f"📊 Latest data - Time: {df_with_supertrend.index[-1]}")
                            logger.info(f"   Price: {latest['close']}, Supertrend: {latest[supertrend_col]}")
                            logger.info(f"   Signal: {latest['signal']}, Changed: {latest.get('signal_change', False)}")
                            
                            # Apply trading strategy
                            apply_trading_strategy(df_with_supertrend, trading_symbol, quantity)
                        else:
                            logger.error("❌ Supertrend calculation failed or returned None")
                    else:
                        logger.warning(f"⚠ Failed to fetch {timeframe_minutes}-minute candle for {candle_start_minute.strftime('%H:%M')}")
                    
                    # Update timing variables
                    last_fetched_candle_time = candle_start_minute
                    fetch_time = current_minute
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                logger.info("🛑 Stop signal received, exiting...")
                break
                
            # Sleep briefly to prevent excessive CPU usage
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        logger.warning("\n⛔ Trading stopped by user.")
    except Exception as e:
        logger.error(f"⚠ Error in trading loop: {str(e)}")
        logger.debug(traceback.format_exc())
    finally:
        # Clean up resources and close any open positions
        clean_up_resources()
        logger.info("🏁 Trading session ended.")
        return True

def topgun(trading_symbol_param, symbol_token_param, exchange_param, quantity_param, instrument_type = None, 
           stop_event=None, api_token=None, stock_name_param=None, candle_duration=1,
           supertrend_length=10, supertrend_factor=2.0, log_level=logging.INFO):
    """Wrapper function for the trading strategy with Supertrend parameters"""
    global stock_name, trading_symbol, symbol_token, exchange, quantity, API_KEY, option_data, CANDLE_SIZE
    global SUPERTREND_LENGTH, SUPERTREND_FACTOR  # Add global variables for Supertrend parameters
    
    # Setup logger with specified log level + a per-session log file (IST timestamp)
    session_start_ist = get_ist_now()
    session_timestamp = session_start_ist.strftime("%Y-%m-%d_%H-%M-%S")
    safe_symbol = "".join(c if c.isalnum() else "_" for c in (trading_symbol_param or "session"))
    session_log_path = os.path.join(
        SESSION_LOGS_DIR,
        f"session_{session_timestamp}_{safe_symbol}.log",
    )

    global logger
    logger = setup_logger(log_level, session_log_path=session_log_path)

    logger.info("=" * 70)
    logger.info(f"🟢 SESSION STARTED at {session_start_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
    logger.info(f"📄 Session log file: {session_log_path}")
    logger.info("=" * 70)

    API_KEY = api_token
    # Set global variables
    stock_name = stock_name_param
    trading_symbol = trading_symbol_param
    symbol_token = symbol_token_param
    exchange = exchange_param
    quantity = int(quantity_param)  # Ensure quantity is an integer
    instrument_type = instrument_type 
    # Set Supertrend parameters
    SUPERTREND_LENGTH = supertrend_length
    SUPERTREND_FACTOR = supertrend_factor
    
    # Set candle size based on duration
    try:
        CANDLE_SIZE = get_candle_size(candle_duration)
        logger.info(f"🕰 Using {candle_duration}-minute candles ({CANDLE_SIZE})")
    except ValueError as e:
        logger.error(f"❌ Invalid candle duration: {e}")
        return False
    
    logger.info(f"🚀 Starting trading bot with:")
    logger.info(f"   Stock Name: {stock_name}")
    logger.info(f"   Symbol: {trading_symbol}")
    logger.info(f"   Token: {symbol_token}")
    logger.info(f"   Exchange: {exchange}")
    logger.info(f"   Quantity: {quantity}")
    logger.info(f"   Instrument Type: {instrument_type}")
    logger.info(f"   Candle Duration: {candle_duration} minutes")
    logger.info(f"   Supertrend Length: {SUPERTREND_LENGTH}")
    logger.info(f"   Supertrend Factor: {SUPERTREND_FACTOR}")
    logger.debug(f"   API Key: {API_KEY}")

    if stock_name in ['SENSEX', 'NIFTY', 'BANKNIFTY']:
        start_time = time.time()
        fetcher = OptionsDataFetcher()
        option_data = fetcher.get_options_data(stock_name)
        if option_data is not None:
            logger.info(f"✅ Loaded {len(option_data)} options contracts")
            logger.debug("\nAvailable options:")
            logger.debug(option_data.head())
        else:
            logger.error("❌ Failed to fetch options data")
        end_time = time.time()
        logger.info(f"Time taken to fetch options data: {end_time - start_time} seconds")
            
    # Reset global state variables
    global active_position, entry_price, trade_history, total_profit_loss
    global current_trade_entry_price, current_trade_entry_time, trade_count, winning_trades, losing_trades
    
    active_position = None
    entry_price = None
    current_trade_entry_price = None
    current_trade_entry_time = None
    
    # Keep existing trade history if continuing a session
    if not hasattr(topgun, 'trade_history_initialized'):
        trade_history = []
        total_profit_loss = 0
        trade_count = 0
        winning_trades = 0
        losing_trades = 0
        topgun.trade_history_initialized = True
    
    try:
        success = main(api_token, stop_event)
        if stop_event and stop_event.is_set():
            logger.info("🛑 Trading stopped gracefully.")
        return success
    except Exception as e:
        logger.error(f"❌ Error in topgun strategy: {str(e)}")
        logger.debug(traceback.format_exc())
        return False
    finally:
        session_end_ist = get_ist_now()
        duration_secs = (session_end_ist - session_start_ist).total_seconds()
        hrs, rem = divmod(int(duration_secs), 3600)
        mins, secs = divmod(rem, 60)
        logger.info("=" * 70)
        logger.info(f"🔴 SESSION STOPPED at {session_end_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
        logger.info(f"⏱  Session duration: {hrs:02d}:{mins:02d}:{secs:02d}")
        logger.info(f"📝 Trading session completed. Log saved to: {session_log_path}")
        logger.info("=" * 70)

        # Flush + close the per-session file handler so the file is fully written
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                try:
                    handler.flush()
                    handler.close()
                except Exception:
                    pass
                logger.removeHandler(handler)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Angel One Trading Bot')
    parser.add_argument('--stock_name', type=str, help='Stock name', required=True)
    parser.add_argument('--symbol', type=str, help='Trading symbol', required=True)
    parser.add_argument('--token', type=str, help='Symbol token', required=True)
    parser.add_argument('--exchange', type=str, default='NSE', help='Exchange (default: NSE)')
    parser.add_argument('--quantity', type=int, default=1, help='Quantity (default: 1)')
    parser.add_argument('--candle-duration', type=int, default=1, choices=[1, 5], help='Candle duration in minutes (default: 1)')
    parser.add_argument('--api-token', type=str, help='API token (optional, will use .env credentials if not provided)')
    parser.add_argument('--log-level', type=str, default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Convert string log level to logging constant
    log_level = getattr(logging, args.log_level)
    
    topgun(
        stock_name_param=args.stock_name,
        trading_symbol_param=args.symbol,
        symbol_token_param=args.token,
        exchange_param=args.exchange,
        quantity_param=args.quantity,
        api_token=args.api_token,
        candle_duration=args.candle_duration,
        log_level=log_level
    )

'''
def get_status_message():
    """Return the current status message."""
    global status_message
    return status_message

def clear_status_message():
    """Clear the current status message."""
    global status_message
    status_message = None
    return True
'''
