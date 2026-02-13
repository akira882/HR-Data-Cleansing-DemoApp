import pandas as pd
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class DataValidator:
    """
    Validates the integrity and quality of HR data.
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.issues: List[Dict] = []

    def validate(self) -> List[Dict]:
        """
        Runs multiple validation checks and returns a list of identified issues.
        """
        logger.info("Starting data validation checks...")
        
        self.check_unrealistic_ages()
        self.check_negative_salaries()
        self.check_future_hire_dates()
        self.check_invalid_departments()
        
        logger.info(f"Validation complete. Found {len(self.issues)} potential issues.")
        return self.issues

    def check_unrealistic_ages(self):
        """Flags records where age is outside [18, 100]."""
        mask = (self.df['age'] < 18) | (self.df['age'] > 100)
        invalid = self.df[mask]
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Unrealistic Age',
                'value': row['age'],
                'severity': 'High'
            })

    def check_negative_salaries(self):
        """Flags records with negative salary values."""
        invalid = self.df[self.df['salary'] < 0]
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Negative Salary',
                'value': row['salary'],
                'severity': 'Critical'
            })

    def check_future_hire_dates(self):
        """Flags hire dates that are in the future relative to today."""
        today = pd.Timestamp.today()
        invalid = self.df[self.df['hire_date'] > today]
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Future Hire Date',
                'value': row['hire_date'],
                'severity': 'Medium'
            })

    def check_invalid_departments(self):
        """Flags rows where department is marked as 'Unassigned'."""
        invalid = self.df[self.df['department'] == 'Unassigned']
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Unassigned Department',
                'value': 'Unassigned',
                'severity': 'Low'
            })
