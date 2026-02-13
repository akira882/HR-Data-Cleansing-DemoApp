import os
import logging
from typing import List, Dict, Any
from anthropic import Anthropic
from dotenv import load_dotenv

# Ensure local environment variables are loaded
load_dotenv()

logger = logging.getLogger(__name__)

class AnomalyDetector:
    """Interprets complex HR data anomalies using Generative AI.
    
    Bridges the gap between raw statistical flags and actionable business 
    recommendations by leveraging the Claude 3.5 Sonnet model.
    """
    
    def __init__(self):
        """Initializes the Anthropic client using environment variables."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not found. AI augmentation will be disabled.")
            self.client = None
        else:
            self.client = Anthropic(api_key=api_key)

    def analyze_issues(self, issues: List[Dict[str, Any]], kpis: Dict[str, Any]) -> str:
        """Generates a professional executive summary of identified risks.
        
        Args:
            issues (List[Dict]): List of anomalies detected by the DataValidator.
            kpis (Dict): Computed metrics from the KPICalculator.
            
        Returns:
            str: Markdown-formatted executive summary and recommendations.
        """
        if not self.client:
            return (
                "### ⚠️ AI Analysis Disabled\n"
                "To enable automatic executive insights, please configure your "
                "`ANTHROPIC_API_KEY` in the `.env` file."
            )

        prompt = self._construct_prompt(issues, kpis)
        
        try:
            logger.info("Engaging Claude 3.5 for heuristic risk analysis...")
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1200,
                temperature=0, # Zero temperature ensures objective, consistent analysis
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"AI Insight Generation Failed: {str(e)}")
            return f"Error generating insights: {str(e)}"

    def _construct_prompt(self, issues: List[Dict[str, Any]], kpis: Dict[str, Any]) -> str:
        """Constructs a high-context prompt for senior-level HR analysis."""
        # Truncate issues to avoid token overflow while maintaining representative samples
        sample_issues = issues[:25]
        issues_str = "\n".join([
            f"- {i['issue_type']} | Value: {i['value']} | Severity: {i['severity']} (EMP: {i['employee_id']})" 
            for i in sample_issues
        ])
        
        return f"""
        Execute as a Senior People Analytics Strategy Consultant.
        
        Objective: Analyze the provided HR data indicators and synthesize an executive-level risk summary.
        
        ### KPI Snapshot:
        - Current Headcount: {kpis.get('headcount')}
        - Attrition Rate: {kpis.get('attrition_rate')}%
        - Avg Workforce Age: {kpis.get('average_age')}
        - Avg Organizational Tenure: {kpis.get('average_tenure')} years
        
        ### Identified Data Anomaly Stream:
        {issues_str}
        
        ### Requirements for Response:
        1. **Data Integrity Audit**: Summarize the quality of the incoming data stream.
        2. **Risk Identification**: Identify 3 strategic risks (e.g., turnover contagion, demographic gaps).
        3. **Strategic Recommendations**: Provide 4 actionable, business-centric recommendations.
        
        Tone: Professional, Data-driven, Direct.
        Output Language: Japanese (日本語).
        """
