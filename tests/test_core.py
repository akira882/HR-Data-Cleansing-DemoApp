import pytest
import pandas as pd
from src.data_cleaning import HRDataCleaner
from src.kpi_calculator import KPICalculator

def test_data_cleaning_duplicates():
    df = pd.DataFrame({
        'employee_id': ['EMP-1', 'EMP-1'],
        'department': ['HR', 'HR']
    })
    cleaner = HRDataCleaner(df)
    cleaned = cleaner.clean_all()
    assert len(cleaned) == 1

def test_data_cleaning_missing_dept():
    df = pd.DataFrame({
        'employee_id': ['EMP-1'],
        'department': [None]
    })
    cleaner = HRDataCleaner(df)
    cleaned = cleaner.clean_all()
    assert cleaned.iloc[0]['department'] == 'Unassigned'

def test_kpi_headcount():
    df = pd.DataFrame({
        'employee_id': ['EMP-1', 'EMP-2'],
        'status': ['Active', 'Terminated'],
        'is_active': [1, 0],
        'age': [30, 40],
        'hire_date': [pd.Timestamp('2020-01-01'), pd.Timestamp('2021-01-01')],
        'department': ['Sales', 'Sales']
    })
    calc = KPICalculator(df)
    kpis = calc.calculate_all()
    assert kpis['headcount'] == 1
    assert kpis['attrition_rate'] == 50.0

def test_kpi_average_age():
    df = pd.DataFrame({
        'age': [20, 30, 40],
        'is_active': [1, 1, 1],
        'status': ['Active', 'Active', 'Active'],
        'hire_date': [pd.Timestamp('2020-01-01')] * 3,
        'department': ['HR'] * 3
    })
    calc = KPICalculator(df)
    assert calc.calculate_average_age() == 30.0
