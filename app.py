import streamlit as st
import pandas as pd
import os
from src.data_cleaning import HRDataCleaner
from src.validation import DataValidator
from src.kpi_calculator import KPICalculator
from src.anomaly_detection import AnomalyDetector
from src.report_generator import ReportGenerator
from src.dashboard_ui import DashboardUI

# Page Config
st.set_page_config(page_title="HR Data Dashboard", layout="wide")

def load_data():
    raw_data_path = "data/raw_hr_data.csv"
    if not os.path.exists(raw_data_path):
        st.error(f"Data file not found at {raw_data_path}. Please run the generator script first.")
        return None
    return pd.read_csv(raw_data_path)

def main():
    ui = DashboardUI()
    ui.render_header()
    
    # sidebar
    st.sidebar.header("コントロールパネル")
    if st.sidebar.button("データを更新"):
        st.cache_data.clear()
        st.rerun()

    # Data Pipeline
    raw_df = load_data()
    if raw_df is None:
        return

    # 1. Cleaning
    cleaner = HRDataCleaner(raw_df)
    cleaned_df = cleaner.clean_all()
    
    # 2. Validation
    validator = DataValidator(cleaned_df)
    issues = validator.validate()
    
    # 3. KPI Calculation
    calculator = KPICalculator(cleaned_df)
    kpis = calculator.calculate_all()
    
    # --- UI Rendering ---
    
    # Row 1: Metrics
    ui.render_metrics(kpis)
    
    # Row 2: Alerts
    ui.render_anomaly_alerts(issues)
    
    # Row 3: Charts
    col1, col2 = st.columns(2)
    with col1:
        ui.plot_dept_headcount(kpis['dept_headcount'])
    with col2:
        ui.plot_age_distribution(cleaned_df)

    # Row 4: AI Insights
    st.divider()
    st.subheader("🤖 AI エグゼクティブ・インサイト (Powered by Claude)")
    
    detector = AnomalyDetector()
    
    if st.button("AI分析 & PDFレポートを生成"):
        with st.spinner("Claudeがデータを分析中..."):
            insights = detector.analyze_issues(issues, kpis)
            st.markdown(insights)
            
            # Generate PDF
            report_gen = ReportGenerator()
            pdf_path = report_gen.generate_pdf(kpis, insights)
            
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="PDFレポートをダウンロード",
                    data=f,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf"
                )

if __name__ == "__main__":
    main()
