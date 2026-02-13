import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class KPICalculator:
    """
    Calculates key HR performance indicators from a cleaned dataset.
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def calculate_all(self) -> Dict[str, Any]:
        """
        Runs all KPI calculations and returns a summary dictionary.
        """
        logger.info("Calculating HR KPIs...")
        
        kpis = {
            'headcount': self.calculate_headcount(),
            'dept_headcount': self.calculate_dept_headcount(),
            'attrition_rate': self.calculate_attrition_rate(),
            'average_age': self.calculate_average_age(),
            'average_tenure': self.calculate_average_tenure_years()
        }
        
        logger.info("KPI calculations complete.")
        return kpis

    def calculate_headcount(self) -> int:
        """Returns total active headcount."""
        return int(self.df[self.df['is_active'] == 1].shape[0])

    def calculate_dept_headcount(self) -> Dict[str, int]:
        """Returns headcount distribution by department."""
        return self.df[self.df['is_active'] == 1]['department'].value_counts().to_dict()

    def calculate_attrition_rate(self) -> float:
        """Calculates attrition rate (Terminated / Total)."""
        total = len(self.df)
        if total == 0:
            return 0.0
        terminated = len(self.df[self.df['status'] == 'Terminated'])
        return round((terminated / total) * 100, 2)

    def calculate_average_age(self) -> float:
        """Calculates average age of employees."""
        return round(self.df['age'].mean(), 1)

    def calculate_average_tenure_years(self) -> float:
        """Calculates average tenure in years for active employees."""
        active_df = self.df[self.df['is_active'] == 1].copy()
        if active_df.empty:
            return 0.0
            
        today = pd.Timestamp.today()
        # Ensure hire_date is datetime
        active_df['hire_date'] = pd.to_datetime(active_df['hire_date'])
        tenure_days = (today - active_df['hire_date']).dt.days
        return round(tenure_days.mean() / 365.25, 1)

if __name__ == "__main__":
    # Test block
    sample_df = pd.DataFrame({
        'employee_id': ['EMP-1', 'EMP-2', 'EMP-3'],
        'department': ['Engineering', 'Sales', 'Engineering'],
        'age': [30, 40, 35],
        'hire_date': [pd.Timestamp('2020-01-01'), pd.Timestamp('2022-01-01'), pd.Timestamp('2021-01-01')],
        'status': ['Active', 'Active', 'Terminated'],
        'is_active': [1, 1, 0]
    })
    calc = KPICalculator(sample_df)
    print(calc.calculate_all())
