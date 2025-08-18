# Final_code_Part_1.py
import sys
import os

# Add the current directory to the Python path if it's not already there
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import functions from the basic_trading_strategy module
from second_version import topgun, get_trade_history

# Export these functions for use by other modules
__all__ = ['topgun', 'get_trade_history']