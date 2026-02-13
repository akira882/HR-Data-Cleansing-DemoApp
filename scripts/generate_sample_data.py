import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

def generate_hr_data(num_records=500):
    """
    Generates a realistic (but synthetic) HR dataset with some embedded anomalies.
    """
    np.random.seed(42)
    
    # Departments and Roles
    depts = ['Engineering', 'Sales', 'HR', 'Marketing', 'Operations', 'Finance']
    statuses = ['Active', 'Terminated']
    
    # Generate Base Data
    data = {
        'employee_id': [f'EMP-{1000 + i}' for i in range(num_records)],
        'name': [f'Employee {i}' for i in range(num_records)],
        'department': np.random.choice(depts, num_records),
        'age': np.random.randint(22, 65, num_records),
        'salary': np.random.randint(40000, 150000, num_records),
        'hire_date': [datetime(2015, 1, 1) + timedelta(days=np.random.randint(0, 3000)) for i in range(num_records)],
        'status': np.random.choice(statuses, num_records, p=[0.85, 0.15])
    }
    
    df = pd.DataFrame(data)
    
    # Calculate termination date for terminated employees
    df['termination_date'] = df.apply(
        lambda x: x['hire_date'] + timedelta(days=np.random.randint(30, 1000)) if x['status'] == 'Terminated' else None,
        axis=1
    )
    
    # --- Inject Anomalies ---
    
    # 1. Negative Salary (Error)
    df.loc[0, 'salary'] = -50000 
    
    # 2. Unrealistic Age (Anomaly)
    df.loc[1, 'age'] = 150
    
    # 3. Missing Department (Data Cleaning Target)
    df.loc[2, 'department'] = np.nan
    
    # 4. Duplicate Record
    df = pd.concat([df, df.iloc[[5]]], ignore_index=True)
    
    # 5. Future Hire Date (Anomaly)
    df.loc[3, 'hire_date'] = datetime(2030, 12, 25)
    
    # Save to CSV
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    output_dir = os.path.join(project_root, 'data')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'raw_hr_data.csv')
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} records at {output_path}")

if __name__ == "__main__":
    generate_hr_data()
