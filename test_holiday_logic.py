#!/usr/bin/env python3
"""
Test script for trading holiday detection logic
"""
import sys
import datetime
from pathlib import Path

# Add the api directory to the path so we can import our functions
sys.path.append(str(Path(__file__).parent / "api"))

from second_version import is_trading_holiday, is_trading_day, get_last_trading_day

def test_holiday_detection():
    """Test holiday detection with known dates"""
    print("🧪 Testing Holiday Detection Logic")
    print("=" * 50)
    
    # Test cases: (date_string, expected_is_holiday, description)
    test_cases = [
        ("2025-02-26", True, "Mahashivratri (Wednesday)"),
        ("2025-03-14", True, "Holi (Friday)"),
        ("2025-03-15", False, "Day after Holi (Saturday - weekend)"),
        ("2025-03-13", False, "Day before Holi (Thursday - normal trading day)"),
        ("2025-04-18", True, "Good Friday"),
        ("2025-04-19", False, "Saturday after Good Friday"),
        ("2025-04-21", False, "Monday after Good Friday weekend"),
        ("2025-12-25", True, "Christmas (Thursday)"),
        ("2025-01-15", False, "Normal trading day"),
        ("2025-06-15", False, "Normal Sunday (weekend)"),
    ]
    
    print("Holiday Detection Tests:")
    for date_str, expected_holiday, description in test_cases:
        actual_holiday = is_trading_holiday(date_str)
        status = "✅" if actual_holiday == expected_holiday else "❌"
        print(f"{status} {date_str} ({description}): Expected {expected_holiday}, Got {actual_holiday}")
    
    print("\nTrading Day Tests:")
    trading_day_cases = [
        ("2025-02-26", False, "Mahashivratri (holiday)"),
        ("2025-02-25", True, "Day before Mahashivratri (Tuesday)"),
        ("2025-02-27", True, "Day after Mahashivratri (Thursday)"),
        ("2025-03-15", False, "Saturday (weekend)"),
        ("2025-03-16", False, "Sunday (weekend)"),
        ("2025-03-17", True, "Monday (normal trading day)"),
        ("2025-04-18", False, "Good Friday (holiday)"),
        ("2025-04-19", False, "Saturday after Good Friday"),
        ("2025-04-21", True, "Monday after Good Friday weekend"),
    ]
    
    for date_str, expected_trading, description in trading_day_cases:
        actual_trading = is_trading_day(date_str)
        status = "✅" if actual_trading == expected_trading else "❌"
        print(f"{status} {date_str} ({description}): Expected {expected_trading}, Got {actual_trading}")

def test_last_trading_day():
    """Test getting the last trading day with various scenarios"""
    print("\n" + "=" * 50)
    print("🧪 Testing Last Trading Day Logic")
    print("=" * 50)
    
    # Test cases: (reference_date, expected_scenarios)
    test_scenarios = [
        ("2025-02-27", "Should skip Mahashivratri (2025-02-26) and return 2025-02-25"),
        ("2025-03-15", "Should skip Holi (2025-03-14) and return 2025-03-13"),
        ("2025-03-17", "Should skip weekend and return 2025-03-14... wait, that's Holi! Should return 2025-03-13"),
        ("2025-04-21", "Should skip Good Friday (2025-04-18) and weekend, return 2025-04-17"),
        ("2025-12-26", "Should skip Christmas (2025-12-25) and return 2025-12-24"),
        ("2025-01-15", "Normal Wednesday, should return 2025-01-14 (Tuesday)"),
    ]
    
    for ref_date_str, scenario in test_scenarios:
        ref_date = datetime.datetime.strptime(ref_date_str, '%Y-%m-%d').date()
        last_trading = get_last_trading_day(ref_date)
        
        print(f"\n📅 Reference Date: {ref_date_str}")
        print(f"   Scenario: {scenario}")
        print(f"   Result: {last_trading}")
        
        # Verify the result is actually a trading day
        if last_trading:
            is_valid = is_trading_day(last_trading)
            status = "✅" if is_valid else "❌"
            print(f"   {status} Is the result a valid trading day? {is_valid}")
        else:
            print(f"   ❌ Failed to find a trading day!")

def test_edge_cases():
    """Test edge cases around holidays"""
    print("\n" + "=" * 50)
    print("🧪 Testing Edge Cases")
    print("=" * 50)
    
    # Test a scenario where we have multiple consecutive non-trading days
    print("Testing scenario after a long weekend with holiday:")
    
    # Holi 2025 is on Friday March 14, followed by weekend
    # So March 17 (Monday) should go back to March 13 (Thursday)
    monday_after_holi = datetime.date(2025, 3, 17)
    last_trading = get_last_trading_day(monday_after_holi)
    
    print(f"Monday after Holi weekend: {monday_after_holi}")
    print(f"Expected last trading day: 2025-03-13 (Thursday before Holi)")
    print(f"Actual result: {last_trading}")
    
    expected = datetime.date(2025, 3, 13)
    status = "✅" if last_trading == expected else "❌"
    print(f"{status} Correct result: {last_trading == expected}")

if __name__ == "__main__":
    test_holiday_detection()
    test_last_trading_day()
    test_edge_cases()
    print("\n" + "=" * 50)
    print("🏁 Testing Complete!")