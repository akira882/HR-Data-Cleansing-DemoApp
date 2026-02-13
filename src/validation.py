import pandas as pd
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DataValidator:
    """Performs rigorous integrity checks on HR datasets.
    
    Identifies logical inconsistencies and data entry errors that could 
    compromise the validity of HR metrics and AI-driven insights.
    """
    
    def __init__(self, df: pd.DataFrame):
        """Initializes the validator.
        
        Args:
            df (pd.DataFrame): The cleaned dataset to validate.
        """
        self.df = df
        self.issues: List[Dict[str, Any]] = []

    def validate(self) -> List[Dict[str, Any]]:
        """Executes a suite of validation rules.
        
        Returns:
            List[Dict]: A registry of identified issues with severity levels.
        """
        logger.info("Executing data validation suite...")
        
        self.check_unrealistic_ages()
        self.check_negative_salaries()
        self.check_future_hire_dates()
        self.check_invalid_departments()
        
        logger.info(f"Validation complete. Identified {len(self.issues)} potential risk areas.")
        return self.issues

    def check_unrealistic_ages(self) -> None:
        """Identifies outlier ages (outside [18, 100]).
        
        Ages in this range often indicate data entry errors or legacy system issues.
        """
        mask = (self.df['age'] < 18) | (self.df['age'] > 100)
        invalid = self.df[mask]
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Unrealistic Age',
                'value': row['age'],
                'severity': 'High'
            })

    def check_negative_salaries(self) -> None:
        """Flags erroneous negative salary entries.
        
        Negative values are critical errors that invalidate average compensation reports.
        """
        invalid = self.df[self.df['salary'] < 0]
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Negative Salary',
                'value': row['salary'],
                'severity': 'Critical'
            })

    def check_future_hire_dates(self) -> None:
        """Detects hire dates set in the future.
        
        While sometimes used for planned hires, unexpected future dates skew tenure calculations.
        """
        today = pd.Timestamp.today()
        invalid = self.df[self.df['hire_date'] > today]
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Future Hire Date',
                'value': row['hire_date'].strftime('%Y-%m-%d') if not pd.isnull(row['hire_date']) else 'NaT',
                'severity': 'Medium'
            })

    def check_invalid_departments(self) -> None:
        """Flags records with 'Unassigned' departments.
        
        Highlights data gaps that prevent accurate department-level cost allocation.
        """
        invalid = self.df[self.df['department'] == 'Unassigned']
        for _, row in invalid.iterrows():
            self.issues.append({
                'employee_id': row['employee_id'],
                'issue_type': 'Unassigned Department',
                'value': 'Unassigned',
                'severity': 'Low'
            })
