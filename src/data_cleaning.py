import pandas as pd
import logging
from typing import Optional, List
from datetime import datetime

# Configure logging for production traceability
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HRDataCleaner:
    """Handles deep cleaning and standardization of raw HR datasets.
    
    This class implements idempotent data transformation logic to ensure
    that raw HRIS exports are converted into a research-ready format.
    
    Attributes:
        df (pd.DataFrame): The dataset being processed.
    """
    
    def __init__(self, df: pd.DataFrame):
        """Initializes the cleaner with a copy of the input dataframe.
        
        Args:
            df (pd.DataFrame): Raw input data from HRIS/CSV.
        """
        self.df = df.copy()
        
    def clean_all(self) -> pd.DataFrame:
        """Executes the full cleaning pipeline in the correct logical sequence.
        
        Returns:
            pd.DataFrame: A fully cleaned and structured dataframe.
        """
        logger.info("Starting production-grade HR data cleaning pipeline...")
        
        try:
            self.remove_duplicates()
            self.handle_missing_values()
            self.format_dates()
            self.calculate_derived_fields()
            logger.info("Cleaning pipeline successfully completed.")
        except Exception as e:
            logger.error(f"Critical error during data cleaning: {str(e)}")
            raise
            
        return self.df

    def remove_duplicates(self) -> None:
        """Removes duplicate records based on the unique 'employee_id' key.
        
        Identifies and removes redundant entries while keeping the first occurrence.
        """
        initial_count = len(self.df)
        self.df.drop_duplicates(subset=['employee_id'], keep='first', inplace=True)
        dropped_count = initial_count - len(self.df)
        if dropped_count > 0:
            logger.info(f"Identified and removed {dropped_count} duplicate employee records.")

    def handle_missing_values(self) -> None:
        """Implements missing data handling strategies for critical HR fields.
        
        Fills unassigned categorical data to prevent skewing group-by operations.
        """
        if 'department' in self.df.columns:
            missing_dept = self.df['department'].isnull().sum()
            self.df['department'] = self.df['department'].fillna('Unassigned')
            if missing_dept > 0:
                logger.info(f"Imputed 'Unassigned' for {missing_dept} missing department values.")

    def format_dates(self) -> None:
        """Standardizes temporal columns into UTC-neutral datetime objects.
        
        Uses 'coerce' for invalid formats to prevent pipeline crashes, 
        flagging them as NaT for later validation.
        """
        date_cols = ['hire_date', 'termination_date']
        for col in date_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_datetime(self.df[col], errors='coerce')
                logger.debug(f"Normalized temporal column: {col}")

    def calculate_derived_fields(self) -> None:
        """Generates analysis-ready features from raw state data.
        
        Optimizes the dataset for downstream KPI calculation and visualization.
        """
        # Boolean flags are memory-efficient for large-scale filtering
        if 'status' in self.df.columns:
            self.df['is_active'] = self.df['status'].apply(lambda x: 1 if x == 'Active' else 0)
            
        # Numerical coercion ensures statistical operations (mean/sum) succeed
        if 'age' in self.df.columns:
            self.df['age'] = pd.to_numeric(self.df['age'], errors='coerce')

if __name__ == "__main__":
    # Example usage for CI/CD or manual verification
    sample_df = pd.DataFrame({
        'employee_id': ['EMP-1', 'EMP-1', 'EMP-2'],
        'department': ['Engineering', 'Engineering', None],
        'hire_date': ['2020-01-01', '2020-01-01', '2021-06-15'],
        'status': ['Active', 'Active', 'Terminated']
    })
    cleaner = HRDataCleaner(sample_df)
    result = cleaner.clean_all()
    print(result[['employee_id', 'department', 'is_active']])
