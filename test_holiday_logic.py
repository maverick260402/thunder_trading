#!/usr/bin/env python3
"""
Test script for holiday handling logic in second_version.py
Tests the is_trading_holiday, is_trading_day, and get_last_trading_day functions
"""

import sys
import os
import datetime

# Add the api directory to the path so we can import second_version
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

# Import the functions we want to test
from second_version import (
    is_trading_holiday,
    is_trading_day,
    get_last_trading_day,
    TRADING_HOLIDAYS_2026
)

def test_is_trading_holiday():
    """Test the is_trading_holiday function"""
    print("\n" + "="*60)
    print("Testing is_trading_holiday()")
    print("="*60)

    test_cases = [
        # Format: (date, expected_result, description)
        (datetime.date(2026, 1, 15), True, "Municipal Election - Maharashtra"),
        (datetime.date(2026, 1, 26), True, "Republic Day"),
        (datetime.date(2026, 3, 3), True, "Holi"),
        (datetime.date(2026, 12, 25), True, "Christmas"),
        (datetime.date(2026, 1, 20), False, "Regular Tuesday"),
        (datetime.date(2026, 2, 10), False, "Regular Tuesday"),
        (datetime.date(2026, 5, 15), False, "Regular Friday"),
        # Test with datetime objects
        (datetime.datetime(2026, 1, 26, 10, 30), True, "Republic Day (datetime)"),
        # Test with string
        ("2026-01-26", True, "Republic Day (string)"),
    ]

    passed = 0
    failed = 0

    for date, expected, description in test_cases:
        result = is_trading_holiday(date)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status}: {date} -> {result} (expected {expected}) - {description}")

    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0


def test_is_trading_day():
    """Test the is_trading_day function"""
    print("\n" + "="*60)
    print("Testing is_trading_day()")
    print("="*60)

    test_cases = [
        # Format: (date, expected_result, description)
        # Regular weekdays (not holidays)
        (datetime.date(2026, 1, 20), True, "Regular Tuesday"),
        (datetime.date(2026, 2, 10), True, "Regular Tuesday"),
        (datetime.date(2026, 5, 15), True, "Regular Friday"),
        # Weekends
        (datetime.date(2026, 1, 17), False, "Saturday"),
        (datetime.date(2026, 1, 18), False, "Sunday"),
        (datetime.date(2026, 1, 24), False, "Saturday"),
        (datetime.date(2026, 1, 25), False, "Sunday"),
        # Holidays (weekdays)
        (datetime.date(2026, 1, 15), False, "Municipal Election (Thursday)"),
        (datetime.date(2026, 1, 26), False, "Republic Day (Monday)"),
        (datetime.date(2026, 3, 3), False, "Holi (Tuesday)"),
        (datetime.date(2026, 4, 3), False, "Good Friday"),
        (datetime.date(2026, 12, 25), False, "Christmas (Friday)"),
    ]

    passed = 0
    failed = 0

    for date, expected, description in test_cases:
        result = is_trading_day(date)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result == expected:
            passed += 1
        else:
            failed += 1
        weekday_name = date.strftime("%A")
        print(f"{status}: {date} ({weekday_name}) -> {result} (expected {expected}) - {description}")

    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0


def test_get_last_trading_day():
    """Test the get_last_trading_day function"""
    print("\n" + "="*60)
    print("Testing get_last_trading_day()")
    print("="*60)

    test_cases = [
        # Format: (reference_date, expected_result, description)
        # Simple cases (previous day is a trading day)
        (datetime.date(2026, 1, 21), datetime.date(2026, 1, 20), "Tuesday -> Monday"),
        (datetime.date(2026, 2, 11), datetime.date(2026, 2, 10), "Wednesday -> Tuesday"),

        # Monday -> skip weekend to Friday
        (datetime.date(2026, 1, 19), datetime.date(2026, 1, 16), "Monday -> Friday (skip weekend)"),

        # After a long weekend with holiday
        # Jan 26 (Monday) is Republic Day holiday, so Jan 27 (Tuesday) should go back to Jan 23 (Friday)
        (datetime.date(2026, 1, 27), datetime.date(2026, 1, 23), "Tuesday after Republic Day -> Friday"),

        # After Holi (Mar 3, Tuesday)
        (datetime.date(2026, 3, 4), datetime.date(2026, 3, 2), "Wednesday after Holi -> Monday"),

        # Regular Tuesday (previous day is Monday, a trading day)
        (datetime.date(2026, 1, 20), datetime.date(2026, 1, 19), "Tuesday -> Monday"),
    ]

    passed = 0
    failed = 0

    for reference_date, expected, description in test_cases:
        result = get_last_trading_day(reference_date)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status}: {reference_date} -> {result} (expected {expected}) - {description}")

    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0


def test_holiday_list_validity():
    """Verify that all holidays in the list are on valid dates"""
    print("\n" + "="*60)
    print("Testing TRADING_HOLIDAYS_2026 validity")
    print("="*60)

    print(f"Total holidays in 2026: {len(TRADING_HOLIDAYS_2026)}")
    print("\nVerifying each holiday:")

    all_valid = True
    weekend_holidays = []

    for holiday_str in TRADING_HOLIDAYS_2026:
        try:
            holiday_date = datetime.datetime.strptime(holiday_str, '%Y-%m-%d').date()
            weekday_name = holiday_date.strftime("%A")

            # Check if it's a weekend
            if holiday_date.weekday() >= 5:
                weekend_holidays.append((holiday_str, weekday_name))
                print(f"⚠️  {holiday_str} ({weekday_name}) - Holiday on weekend!")
            else:
                print(f"✅ {holiday_str} ({weekday_name}) - Valid")
        except ValueError as e:
            print(f"❌ {holiday_str} - Invalid date format: {e}")
            all_valid = False

    if weekend_holidays:
        print(f"\n⚠️  Note: {len(weekend_holidays)} holidays fall on weekends (this is okay but unusual)")

    print(f"\n📊 Results: {'All dates valid' if all_valid else 'Some dates invalid'}")
    return all_valid


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("HOLIDAY LOGIC TEST SUITE")
    print("="*60)

    results = []

    # Run all tests
    results.append(("Holiday List Validity", test_holiday_list_validity()))
    results.append(("is_trading_holiday()", test_is_trading_holiday()))
    results.append(("is_trading_day()", test_is_trading_day()))
    results.append(("get_last_trading_day()", test_get_last_trading_day()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("="*60)

    if all_passed:
        print("\n🎉 All tests PASSED! Holiday logic is working correctly.")
        return 0
    else:
        print("\n❌ Some tests FAILED. Please review the failures above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
