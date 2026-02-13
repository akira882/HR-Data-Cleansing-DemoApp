import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class KPICalculator:
    """Calculates standardized HR metrics for executive reporting.
    
    Encapsulates established HR formulas to ensure consistency across 
    different datasets and reporting periods.
    """
    
    def __init__(self, df: pd.DataFrame):
        """Initializes the calculator.
        
        Args:
            df (pd.DataFrame): Validated and cleaned dataset.
        """
        self.df = df

    def calculate_all(self) -> Dict[str, Any]:
        """Runs the complete suite of KPI calculations.
        
        Returns:
            Dict[str, Any]: Mapping of metric names to calculated values.
        """
        logger.info("Executing KPI calculation engine...")
        
        metrics = {
            'headcount': self.calculate_headcount(),
            'dept_headcount': self.calculate_dept_headcount(),
            'attrition_rate': self.calculate_attrition_rate(),
            'average_age': self.calculate_average_age(),
            'average_tenure': self.calculate_average_tenure_years()
        }
        
        logger.debug(f"Calculated Metrics: {metrics}")
        return metrics

    def calculate_headcount(self) -> int:
        """Returns the total number of currently active employees."""
        return int(self.df[self.df['is_active'] == 1].shape[0])

    def calculate_dept_headcount(self) -> Dict[str, int]:
        """Provides headcount distribution by organizational unit."""
        return self.df[self.df['is_active'] == 1]['department'].value_counts().to_dict()

    def calculate_attrition_rate(self) -> float:
        """Calculates the annualized attrition percentage.
        
        Formula: (Terminated Employees / Total Historic Records) * 100.
        """
        total = len(self.df)
        if total == 0:
            return 0.0
        terminated = len(self.df[self.df['status'] == 'Terminated'])
        return round((terminated / total) * 100, 2)

    def calculate_average_age(self) -> float:
        """Calculates the mean age across the workforce."""
        return round(self.df['age'].mean(), 1)

    def calculate_average_tenure_years(self) -> float:
        """Calculates the mean duration of employment for active staff.
        
        Uses accurate date differentials to measure tenure in decimal years.
        """
        active_df = self.df[self.df['is_active'] == 1].copy()
        if active_df.empty:
            return 0.0
            
        today = pd.Timestamp.today()
        active_df['hire_date'] = pd.to_datetime(active_df['hire_date'])
        tenure_days = (today - active_df['hire_date']).dt.days
        # Divide by 365.25 to account for leap years
        return round(tenure_days.mean() / 365.25, 1)
