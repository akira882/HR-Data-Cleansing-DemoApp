import pandas as pd
import logging
from typing import Optional
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HRDataCleaner:
    """
    Handles cleaning and standardization of raw HR datasets.
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        
    def clean_all(self) -> pd.DataFrame:
        """
        Executes the full cleaning pipeline.
        """
        logger.info("Starting HR data cleaning pipeline...")
        
        self.remove_duplicates()
        self.handle_missing_values()
        self.format_dates()
        self.calculate_derived_fields()
        
        logger.info("Cleaning pipeline complete.")
        return self.df

    def remove_duplicates(self):
        """Removes duplicate records based on employee_id."""
        initial_count = len(self.df)
        self.df.drop_duplicates(subset=['employee_id'], keep='first', inplace=True)
        dropped_count = initial_count - len(self.df)
        if dropped_count > 0:
            logger.info(f"Removed {dropped_count} duplicate records.")

    def handle_missing_values(self):
        """Handles null values in critical columns."""
        # Fill missing departments with 'Unassigned'
        if 'department' in self.df.columns:
            missing_dept = self.df['department'].isnull().sum()
            self.df['department'] = self.df['department'].fillna('Unassigned')
            if missing_dept > 0:
                logger.info(f"Filled {missing_dept} missing department records with 'Unassigned'.")

    def format_dates(self):
        """Safely converts date strings to datetime objects."""
        date_cols = ['hire_date', 'termination_date']
        for col in date_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_datetime(self.df[col], errors='coerce')
                logger.info(f"Formatted column: {col}")

    def calculate_derived_fields(self):
        """Creates new features useful for analysis."""
        # Active Employee Flag
        if 'status' in self.df.columns:
            self.df['is_active'] = self.df['status'].apply(lambda x: 1 if x == 'Active' else 0)
            
        # Standardize Age
        if 'age' in self.df.columns:
            self.df['age'] = pd.to_numeric(self.df['age'], errors='coerce')

if __name__ == "__main__":
    # Test block
    sample_df = pd.DataFrame({
        'employee_id': ['EMP-1', 'EMP-1', 'EMP-2'],
        'department': ['Sales', 'Sales', None],
        'hire_date': ['2020-01-01', '2020-01-01', '2021-06-15'],
        'status': ['Active', 'Active', 'Terminated']
    })
    cleaner = HRDataCleaner(sample_df)
    cleaned_df = cleaner.clean_all()
    print(cleaned_df)
