import pandas as pd
from pathlib import Path
from typing import List, Tuple

from core.logger import get_logger

logger = get_logger(__name__)

class DataLoader:
    """Loads and preprocesses OHLCV historical data from CSV files."""
    
    def __init__(self, data_folder: str):
        """
        Initialize the DataLoader.
        
        Args:
            data_folder: Path to the directory containing CSV files.
        """
        self.data_folder = Path(data_folder)
        if not self.data_folder.exists():
            logger.warning(f"Data folder '{self.data_folder}' does not exist.")
            
    def get_available_files(self) -> List[Path]:
        """Get a list of all CSV files in the data folder."""
        if not self.data_folder.exists():
            return []
        return sorted(list(self.data_folder.glob("*.csv")))
        
    def parse_filename(self, filepath: Path) -> Tuple[str, str]:
        """
        Parse the symbol and timeframe from the filename (e.g., BTCUSDT_1h.csv).
        
        Args:
            filepath: Path to the CSV file.
            
        Returns:
            Tuple of (symbol, timeframe).
        """
        filename = filepath.stem
        parts = filename.split('_')
        if len(parts) >= 2:
            symbol = parts[0]
            timeframe = parts[1]
            return symbol, timeframe
        return filename, "unknown"
        
    def load_data(self, filepath: Path) -> pd.DataFrame:
        """
        Load OHLCV data from a CSV file.
        
        Args:
            filepath: Path to the CSV file.
            
        Returns:
            DataFrame containing the loaded data.
        """
        try:
            # Expected columns: time, open, high, low, close, volume (or similar)
            df = pd.read_csv(filepath)
            
            # Ensure columns are lower case and strip whitespace
            df.columns = [col.strip().lower() for col in df.columns]
            
            # Accept 'date' column alone (daily CSVs from Delta have no 'time' column)
            if 'time' not in df.columns and 'date' not in df.columns:
                logger.error(f"Missing 'time' column in {filepath}")
                raise ValueError(f"Missing 'time' column in {filepath}")

            # Combine date and time if both present; otherwise use whichever exists
            if 'date' in df.columns and 'time' in df.columns:
                datetime_str = df['date'].astype(str) + ' ' + df['time'].astype(str)
            elif 'date' in df.columns:
                datetime_str = df['date'].astype(str)
            else:
                datetime_str = df['time']

            # Convert to datetime.
            try:
                df['time'] = pd.to_datetime(datetime_str, utc=True, format='mixed', dayfirst=True)
            except Exception as e:
                df['time'] = pd.to_datetime(datetime_str, format='mixed', dayfirst=True)
            
            # Convert timezone-aware/naive datetimes to Unix epoch seconds (float)
            # We explicitly cast to 'datetime64[s]' to handle ns/us/ms resolutions robustly
            df['time'] = df['time'].dt.floor('s').astype('int64') // 10**9
            
            # Sort by time to ensure chronological order
            df = df.sort_values('time').reset_index(drop=True)
            
            # Ensure numeric types for OHLCV
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    
            # Check for missing values
            if df.isnull().values.any():
                logger.warning(f"Found missing values in {filepath.name}, filling forward.")
                df = df.fillna(method='ffill')
                df = df.dropna()  # drop any remaining at the start
                
            logger.info(f"Loaded {len(df)} rows from {filepath.name}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load data from {filepath}: {e}")
            raise
