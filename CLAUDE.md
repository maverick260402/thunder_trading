# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Thunder Trading is a Flask-based web application that provides an automated trading bot for Indian stock markets via Angel One API integration. The application implements a Supertrend-based trading strategy with a web dashboard for monitoring and control.

## Architecture

### Core Components

- **Flask Web Server** (`api/app.py`): Main application server with REST API endpoints, session management, and threading for concurrent trading
- **Trading Engine** (`api/second_version.py`): Core trading logic implementing Supertrend strategy, API authentication, and position management
- **Options Data Handler** (`api/select_option.py`): Manages fetching and caching of options data from Angel One
- **Frontend** (`templates/index.html`, `static/main.js`, `static/style.css`): Web dashboard for trading control and monitoring

### Key Features

- Real-time trading using Supertrend technical indicator
- Multi-timeframe candle analysis (1min, 5min, 15min, 30min, 1hour, 1day)
- Options and equity trading support
- Position tracking and P&L calculation
- Web-based dashboard with real-time status updates
- Thread-safe trading execution with stop/start controls
- **Holiday-aware historical data fetching** - automatically skips Indian trading holidays and weekends when fetching previous session data

## Environment Setup

### Required Environment Variables (.env file)
```
ANGELONE_CLIENT_ID=your_client_id
ANGELONE_MPIN=your_mpin
ANGELONE_TOTP_SECRET=your_totp_secret
ANGELONE_API_KEY=your_api_key
SECRET_KEY=your_flask_secret_key
PORT=5000
```

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application
```bash
# Development
python api/app.py

# Production (using gunicorn)
gunicorn --bind 0.0.0.0:5000 api.app:app
```

## Key API Endpoints

- `POST /apply_supertrend` - Start trading with Supertrend strategy
- `POST /stop_supertrend` - Stop active trading
- `GET /trading_status` - Get current trading status
- `POST /validate_token` - Validate Angel One API token
- `GET /get_stock_data` - Fetch stock master data

## Development Notes

### Threading Architecture
The application uses Python threading for concurrent trading execution. The main Flask thread handles web requests while a separate daemon thread runs the trading logic. Thread communication is managed via `threading.Event()` for clean shutdown.

**Thread Safety Implementation**: Critical global variables are protected with thread locks to prevent race conditions:
- **position_lock**: Protects `active_position`, `entry_price`, `current_trade_entry_price`, `current_trade_entry_time`
- **trade_data_lock**: Protects `trade_history`, `total_profit_loss`, `trade_count`, `winning_trades`, `losing_trades`
- **auth_lock**: Protects `auth_token`, `headers`, `auth_time`
- **config_lock**: For trading configuration variables

Thread-safe wrapper functions available: `safe_get_position_info()`, `safe_set_position()`, `safe_clear_position()`, `safe_get_trade_stats()`, `safe_add_trade()`, `safe_update_auth_token()`, `safe_get_auth_info()` in `second_version.py:182-250`

### Authentication Flow
1. Web login using hardcoded credentials (username: "topgun", password: "maverick")
2. Angel One API authentication using TOTP-based login
3. Session-based token management with automatic refresh

### Trading Strategy
The Supertrend strategy implementation:
- Fetches historical candle data from Angel One API with holiday-aware logic
- Calculates Supertrend indicator using configurable length and factor parameters
- Executes buy/sell orders based on Supertrend signals
- Maintains position tracking and implements basic risk management

### Holiday Handling
The system includes comprehensive Indian market holiday handling:
- **Trading holidays list** for 2025 stored in `TRADING_HOLIDAYS_2025` constant
- **Smart date selection** via `get_last_trading_day()` function that skips holidays and weekends
- **Fallback logic** to prevent failures if holiday detection encounters issues
- **Automatic detection** of trading vs non-trading days using `is_trading_day()` function
- **Integrated market hours logic** - `is_market_open()` function now uses holiday detection
- **Historical data fetching** automatically skips holidays when determining previous trading sessions
- Key functions: `is_trading_holiday()`, `is_trading_day()`, `get_last_trading_day()`, `is_market_open()` in `second_version.py:93-173, 1519-1549`

### Error Handling
- Comprehensive logging using Python logging module
- API request retry logic with exponential backoff
- Graceful handling of network timeouts and connection errors
- Thread-safe error propagation between trading and web threads

## Testing

No formal test suite exists. Manual testing through the web dashboard is the current approach.

## File Structure Notes

- `api/Final_code_Part_1.py` - Simple import wrapper for the main trading functions
- `static/OpenAPIScripMaster.json` - Cached stock master data (if present)
- Logging is configured for cloud deployment (stdout only, no file logging)