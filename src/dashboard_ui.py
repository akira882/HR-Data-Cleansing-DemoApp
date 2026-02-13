import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Dict

class DashboardUI:
    """
    Contains reusable UI components and chart generators for the Streamlit dashboard.
    """
    
    @staticmethod
    def render_header():
        st.title("📊 ヒューマンキャピタル・ダッシュボード")
        st.markdown("""
        *実務特化型 HRアナリティクス & データクリーニング・システム*
        """)
        st.divider()

    @staticmethod
    def render_metrics(kpis: Dict):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("総従業員数", kpis['headcount'])
        col2.metric("離職率", f"{kpis['attrition_rate']}%")
        col3.metric("平均年齢", kpis['average_age'])
        col4.metric("平均勤続年数", kpis['average_tenure'])

    @staticmethod
    def plot_dept_headcount(dept_data: Dict):
        df = pd.DataFrame(list(dept_data.items()), columns=['Department', 'Headcount'])
        fig = px.bar(df, x='Department', y='Headcount', title="部署別従業員数",
                     labels={'Department': '部署', 'Headcount': '人数'},
                     color='Department', color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)

    @staticmethod
    def plot_age_distribution(df: pd.DataFrame):
        fig = px.histogram(df[df['is_active'] == 1], x='age', nbins=20, 
                           title="年齢分布 (現職者)",
                           labels={'age': '年齢', 'count': '人数'},
                           color_discrete_sequence=['#636EFA'])
        st.plotly_chart(fig, use_container_width=True)

    @staticmethod
    def render_anomaly_alerts(issues: list):
        if not issues:
            st.success("✅ 重大なデータ異常は見つかりませんでした。")
            return

        st.warning(f"⚠️ 注意が必要なデータ異常が {len(issues)} 件検出されました。")
        with st.expander("異常値の詳細を表示"):
            issue_df = pd.DataFrame(issues)
            # Translate column names for display
            issue_df.rename(columns={
                'employee_id': '従業員ID',
                'issue_type': '異常の種類',
                'value': '値',
                'severity': '重要度'
            }, inplace=True)
            st.table(issue_df)
