import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, List
import os
from datetime import datetime, timedelta

# Made Class For easy Import
class OptionsDataFetcher:
    def __init__(self):
        self.session = self._create_session()
        self.base_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        self._data: Optional[pd.DataFrame] = None
        self.master_cache_file = 'master_data_cache.csv'
        self.master_cache_timestamp_file = 'master_data_cache_timestamp.txt'
        self._load_cached_master_data()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        return session

    def _load_cached_master_data(self, max_age_hours: int = 24) -> bool:
        """Load master data from cache if it exists and is fresh"""
        if not os.path.exists(self.master_cache_file) or not os.path.exists(self.master_cache_timestamp_file):
            return False

        try:
            # Check if cache is fresh
            with open(self.master_cache_timestamp_file, 'r') as f:
                timestamp = datetime.fromisoformat(f.read().strip())
            
            if datetime.now() - timestamp < timedelta(hours=max_age_hours):
                # Define dtypes for known columns to prevent mixed type warnings
                dtype_dict = {
                    'token': str,  # Token should be string to preserve leading zeros
                    'symbol': str,
                    'name': str,
                    'expiry': str,
                    'strike': float,
                    'lotsize': int,
                    'instrumenttype': str,
                    'exch_seg': str
                }
                self._data = pd.read_csv(self.master_cache_file, dtype=dtype_dict, low_memory=False)
                return True
        except Exception as e:
            print(f"Error loading cached master data: {e}")
        return False

    def _save_master_data_cache(self) -> bool:
        """Save master data to cache"""
        try:
            if self._data is not None:
                self._data.to_csv(self.master_cache_file, index=False)
                with open(self.master_cache_timestamp_file, 'w') as f:
                    f.write(datetime.now().isoformat())
                return True
        except Exception as e:
            print(f"Error saving master data cache: {e}")
        return False

    def fetch_master_data(self) -> bool:
        # Try to load from cache first
        if self._load_cached_master_data():
            return True

        try:
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            # Convert token to string when creating DataFrame to preserve leading zeros
            data = response.json()
            for item in data:
                if 'token' in item:
                    item['token'] = str(item['token'])
            self._data = pd.DataFrame(data)
            # Save to cache after successful fetch
            self._save_master_data_cache()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False

    def get_options_data(self, name: str) -> Optional[pd.DataFrame]:
        if self._data is None:
            if not self.fetch_master_data():
                return None

        try:
            options_data = self._data[
                (self._data['instrumenttype'] == 'OPTIDX') & 
                (self._data['name'] == name)
            ]

            if options_data.empty:
                print(f"No options data found for {name}")
                return None

            result = options_data.sort_values(['expiry', 'strike'])[ 
                ['token', 'symbol', 'name', 'expiry', 'strike', 'lotsize', 'instrumenttype', 'exch_seg']
            ]
            return result

        except Exception as e:
            print(f"Error processing options data: {e}")
            return None

    def load_or_fetch_data(self, name: str, max_age_hours: int = 24) -> Optional[pd.DataFrame]:
        filename = f'{name.lower()}_options.csv'

        # Check if cached file is fresh
        if os.path.exists(filename):
            last_modified = datetime.fromtimestamp(os.path.getmtime(filename))
            if datetime.now() - last_modified < timedelta(hours=max_age_hours):
                try:
                    return pd.read_csv(filename)
                except Exception as e:
                    print(f"Failed to load cache: {e}")

        # Fetch fresh and save
        if not self.fetch_master_data():
            return None

        options_data = self.get_options_data(name)
        if options_data is not None:
            options_data.to_csv(filename, index=False)
        return options_data

    def get_available_expiries(self, name: str) -> Optional[List[str]]:
        options_data = self.load_or_fetch_data(name)
        if options_data is not None:
            return sorted(options_data['expiry'].unique().tolist())
        return None

    def save_to_csv(self, name: str, output_file: Optional[str] = None) -> bool:
        options_data = self.load_or_fetch_data(name)
        if options_data is None:
            return False

        try:
            if output_file is None:
                output_file = f'{name.lower()}_options.csv'

            options_data.to_csv(output_file, index=False)
            print(f"Data saved to '{output_file}'")
            return True
        except Exception as e:
            print(f"Error saving to CSV: {e}")
            return False

# Example usage
if __name__ == "__main__":
    fetcher = OptionsDataFetcher()

    nifty_data = fetcher.load_or_fetch_data("NIFTY")
    if nifty_data is not None:
        print("\nSample of NIFTY options:")
        print(nifty_data.head())

    expiries = fetcher.get_available_expiries("BANKNIFTY")
    if expiries is not None:
        print("\nBANKNIFTY expiry dates:")
        print(expiries)

    fetcher.save_to_csv("NIFTY")
