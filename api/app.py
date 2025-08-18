from flask import Flask, request, jsonify, session, render_template, send_from_directory
import threading
from Final_code_Part_1 import topgun
from flask_cors import CORS
import os
from dotenv import load_dotenv
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

app = Flask(__name__, static_folder='../static', template_folder='../templates')
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Global variables for thread management
trading_thread = None
stop_event = threading.Event()
trading_active = False
last_trading_config = None  # Store last used trading configuration

# Dummy credentials
USERNAME = "topgun"
PASSWORD = "maverick"

# Store API keys temporarily in memory
#api_keys = {}

def start_trading(trading_symbol, symbol_token, exchange, quantity, instrument_type, api_token=None, 
                  name=None, candle_duration=1, supertrend_length=10, supertrend_factor=2.0):
    """Start trading in a separate thread with proper cleanup"""
    global trading_thread, stop_event, trading_active, last_trading_config
    
    # Stop any existing trading thread
    if trading_thread and trading_thread.is_alive():
        stop_event.set()
        trading_thread.join(timeout=5)
    
    # Store the current configuration
    last_trading_config = {
        "trading_symbol": trading_symbol,
        "symbol_token": symbol_token,
        "exchange": exchange,
        "quantity": quantity,
        "instrument_type": instrument_type,
        "candle_duration": candle_duration,
        "api_token": "[redacted]" if api_token else None,
        "name": name,
        "supertrend_length": supertrend_length,
        "supertrend_factor": supertrend_factor
    }
    
    # Reset event and start new thread
    stop_event.clear()
    trading_thread = threading.Thread(
        target=topgun,
        kwargs={
            'trading_symbol_param': trading_symbol,
            'symbol_token_param': symbol_token,
            'exchange_param': exchange,
            'quantity_param': quantity,
            'instrument_type': instrument_type,
            'stop_event': stop_event,
            'api_token': api_token,
            'stock_name_param': name,
            'candle_duration': candle_duration,
            'supertrend_length': supertrend_length,
            'supertrend_factor': supertrend_factor
        },
        daemon=True
    )
    trading_thread.start()
    trading_active = True
    return trading_thread

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('../static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if username == USERNAME and password == PASSWORD:
        session['user'] = username
        return jsonify({"message": "Login successful", "token": "dummy_token"}), 200
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return jsonify({"message": "Unauthorized"}), 401
    return jsonify({"message": f"Welcome {session['user']} to the dashboard!"}), 200

@app.route('/static/OpenAPIScripMaster.json')
def serve_stock_data():
    """Serve the stock data JSON file"""
    try:
        with open('../static/OpenAPIScripMaster.json', 'r') as f:
            stock_data = json.load(f)
        return jsonify(stock_data)
    except Exception as e:
        return jsonify({"error": f"Could not load stock data: {str(e)}"}), 500

@app.route("/validate_token", methods=["POST"])
def validate_token():
    """API endpoint to validate and store API token"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    api_token = data.get("api_token")
    
    if not api_token:
        return jsonify({"error": "API token is required"}), 400
    
    # In a real implementation, you would validate this token with Angel One
    # For now, just store it in memory with the user's session ID
    session_id = session.get('user', 'anonymous')
    #api_keys[session_id] = api_token
    
    return jsonify({
        "message": "API token validated and stored successfully",
        "token_status": "valid"
    }), 200

@app.route("/refresh_token", methods=["POST"])
def refresh_token():
    """API endpoint to refresh API token - in a real app, this would interact with Angel One"""
    session_id = session.get('user', 'anonymous')
    
    # Check if user has a token
    #if session_id not in api_keys:
        #return jsonify({"error": "No token found for this session"}), 404
    
    # In a real implementation, you would request a new token from Angel One
    # For now, just return the same token
    #current_token = api_keys[session_id]
    
    return jsonify({
        "message": "Token refreshed successfully",
        #"new_token": current_token  # In a real app, this would be the refreshed token
    }), 200

@app.route("/apply_supertrend", methods=["POST"])
def apply_supertrend():
    """API endpoint to trigger the Supertrend calculation"""
    global trading_active
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    trading_symbol = data.get("tradingsymbol")
    symbol_token = data.get("symboltoken")
    exchange = data.get("exchange", "NSE")
    quantity = data.get("quantity")
    api_token = os.getenv("ANGELONE_API_KEY")
    name = data.get("name")
    candle_duration = int(data.get("candle_duration", 1))
    instrument_type = data.get("instrument_type")
    
    # Get Supertrend parameters from request
    supertrend_length = int(data.get("supertrend_length", 10))
    supertrend_factor = float(data.get("supertrend_factor", 2.0))

    if not all([trading_symbol, symbol_token, quantity]):
        return jsonify({"error": "Missing required parameters"}), 400

    # Validate API token
    session_id = session.get('user', 'anonymous')
    #stored_token = api_keys.get(session_id)
    
    #if not stored_token or stored_token != api_token:
        #return jsonify({"error": "Invalid API token"}), 401

    if trading_active:
        return jsonify({"error": "Trading already active"}), 400

    try:
        # Pass the API token, candle duration and Supertrend parameters to the trading function
        start_trading(
            trading_symbol, 
            symbol_token, 
            exchange, 
            int(quantity), 
            instrument_type,
            api_token, 
            name, 
            candle_duration,
            supertrend_length,
            supertrend_factor
        )
        return jsonify({
            "message": "Supertrend strategy started successfully",
            "trading_symbol": trading_symbol,
            "symbol_token": symbol_token,
            "candle_duration": candle_duration,
            "supertrend_length": supertrend_length,
            "supertrend_factor": supertrend_factor
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to start trading: {str(e)}"}), 500
    
@app.route("/stop_supertrend", methods=["POST"])
def stop_trading():
    """API endpoint to stop trading"""
    global trading_active, stop_event
    
    # Validate API token
    #data = request.get_json() if request.is_json else {}
    #api_token = os.getenv("ANGELONE_API_KEY")
    #session_id = session.get('user', 'anonymous')
    #stored_token = api_keys.get(session_id)
    #if api_token and (not stored_token or stored_token != api_token):
        #return jsonify({"error": "Invalid API token"}), 401

    if not trading_active:
        return jsonify({"message": "No active trading to stop"}), 200

    try:
        stop_event.set()
        if trading_thread:
            trading_thread.join(timeout=3)  # Wait for thread to terminate
        trading_active = False
        
        return jsonify({
            "message": "Trading stopped successfully", 
            "last_config": last_trading_config
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to stop trading: {str(e)}"}), 500

@app.route('/get_stock_data')
def get_stock_data():
    """Fetch stock data directly from Angel Broking's API"""
    # Create a session with retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    
    try:
        # Fetch data from Angel Broking's API
        response = session.get(
            'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json',
            timeout=10
        )
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Parse and return the JSON data
        stock_data = response.json()
        return jsonify(stock_data)
        
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error fetching stock data: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route("/trading_status", methods=["GET"])
def trading_status():
    """Check trading status - PUBLIC endpoint that doesn't require authentication for basic status"""
    global last_trading_config
    
    # Check if API token is provided for detailed information
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    
    # Validate token if provided
    #session_id = session.get('user', 'anonymous')
    #stored_token = api_keys.get(session_id)
    #token_valid = token and stored_token and stored_token == token
    
    # Basic trading status (always available)
    response_data = {
        "active": trading_active,
    }
    
    # If trading is active, provide basic info without requiring authentication
    if trading_active and last_trading_config:
        response_data.update({
            "symbol": last_trading_config.get("trading_symbol"),
            "token": last_trading_config.get("symbol_token"),
            "exchange": last_trading_config.get("exchange"),
            "quantity": last_trading_config.get("quantity"),
            "candle_duration": last_trading_config.get("candle_duration", 1),
            "name": last_trading_config.get("name"),
            "supertrend_length": last_trading_config.get("supertrend_length", 10),
            "supertrend_factor": last_trading_config.get("supertrend_factor", 2.0)
        })
    
    # Additional info only if token is valid
    #if token_valid:
    response_data["api_token_status"] = "valid"
    response_data["authenticated"] = True
    #else:
        #response_data["api_token_status"] = "missing" if not token else "invalid"
        #response_data["authenticated"] = False
    
    return jsonify(response_data), 200

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000)) # Get port from environment variable or default to 5000
    app.run(host="0.0.0.0", port=port, threaded=True)
