#!/usr/bin/env python3
"""
Simple test for trading holiday detection logic without dependencies
"""
import datetime

# Copy the holiday detection functions here for testing
TRADING_HOLIDAYS_2025 = [
    "2025-02-26",  # Mahashivratri
    "2025-03-14",  # Holi
    "2025-03-31",  # Id-Ul-Fitr (Ramadan Eid)
    "2025-04-10",  # Shri Mahavir Jayanti
    "2025-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-08-15",  # Independence Day / Parsi New Year
    "2025-08-27",  # Shri Ganesh Chaturthi
    "2025-10-02",  # Mahatma Gandhi Jayanti/Dussehra
    "2025-10-21",  # Diwali Laxmi Pujan
    "2025-10-22",  # Balipratipada
    "2025-11-05",  # Prakash Gurpurb Sri Guru Nanak Dev
    "2025-12-25",  # Christmas
]

def is_trading_holiday(date):
    """Check if a given date is a trading holiday"""
    if isinstance(date, datetime.datetime):
        date_str = date.strftime('%Y-%m-%d')
    elif isinstance(date, datetime.date):
        date_str = date.strftime('%Y-%m-%d')
    else:
        date_str = str(date)
    
    return date_str in TRADING_HOLIDAYS_2025

def is_trading_day(date):
    """Check if a given date is a trading day (not weekend and not holiday)"""
    if isinstance(date, datetime.datetime):
        weekday = date.weekday()
        date_obj = date.date()
    elif isinstance(date, datetime.date):
        weekday = date.weekday()
        date_obj = date
    else:
        # Assume it's a string, try to parse it
        try:
            parsed_date = datetime.datetime.strptime(str(date), '%Y-%m-%d').date()
            weekday = parsed_date.weekday()
            date_obj = parsed_date
        except ValueError:
            print(f"❌ Unable to parse date: {date}")
            return False
    
    # Check if it's a weekend (Saturday=5, Sunday=6)
    if weekday >= 5:
        return False
    
    # Check if it's a trading holiday
    if is_trading_holiday(date_obj):
        return False
    
    return True

def get_last_trading_day(reference_date=None):
    """Get the last trading day before the reference date"""
    if reference_date is None:
        reference_date = datetime.date.today()
    elif isinstance(reference_date, datetime.datetime):
        reference_date = reference_date.date()
    
    # Start from the day before the reference date
    check_date = reference_date - datetime.timedelta(days=1)
    
    # Keep going back until we find a trading day
    max_days_back = 10  # Safety limit to prevent infinite loop
    days_checked = 0
    
    while days_checked < max_days_back:
        if is_trading_day(check_date):
            print(f"📅 Last trading day found: {check_date} (checked {days_checked + 1} days back)")
            return check_date
        
        check_date = check_date - datetime.timedelta(days=1)
        days_checked += 1
    
    print(f"❌ Could not find a trading day within {max_days_back} days before {reference_date}")
    return None

def run_tests():
    print("🧪 Testing Holiday Detection Logic")
    print("=" * 50)
    
    # Test key scenarios
    test_cases = [
        # (reference_date, description)
        ("2025-02-27", "Day after Mahashivratri"),
        ("2025-03-15", "Saturday after Holi (Friday)"),
        ("2025-03-17", "Monday after Holi weekend"),
        ("2025-04-21", "Monday after Good Friday weekend"),
        ("2025-01-15", "Normal Wednesday"),
    ]
    
    for ref_date_str, description in test_cases:
        print(f"\n📅 Testing: {ref_date_str} ({description})")
        ref_date = datetime.datetime.strptime(ref_date_str, '%Y-%m-%d').date()
        
        print(f"   Is {ref_date_str} a holiday? {is_trading_holiday(ref_date)}")
        print(f"   Is {ref_date_str} a trading day? {is_trading_day(ref_date)}")
        
        last_trading = get_last_trading_day(ref_date)
        if last_trading:
            print(f"   ✅ Last trading day: {last_trading}")
            print(f"   ✅ Verification - Is {last_trading} a trading day? {is_trading_day(last_trading)}")
        else:
            print(f"   ❌ Failed to find last trading day")

if __name__ == "__main__":
    run_tests()