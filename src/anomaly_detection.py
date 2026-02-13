import os
import logging
from typing import List, Dict, Any
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class AnomalyDetector:
    """
    Leverages Claude API to interpret HR data anomalies and suggest insights.
    """
    
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not found in environment. AI insights will be disabled.")
            self.client = None
        else:
            self.client = Anthropic(api_key=api_key)

    def analyze_issues(self, issues: List[Dict], kpis: Dict[str, Any]) -> str:
        """
        Sends data issues and KPIs to Claude for analysis.
        """
        if not self.client:
            return "AI Analysis is disabled because the API key is missing. Please set ANTHROPIC_API_KEY in your .env file."

        prompt = self._construct_prompt(issues, kpis)
        
        try:
            logger.info("requesting AI analysis from Claude...")
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1000,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return f"Error generating AI insights: {str(e)}"

    def _construct_prompt(self, issues: List[Dict], kpis: Dict[str, Any]) -> str:
        """
        Constructs a structured prompt for the AI.
        """
        issues_str = "\n".join([f"- {i['issue_type']} (Value: {i['value']}, Severity: {i['severity']}) for EMP ID: {i['employee_id']}" for i in issues[:20]])
        
        prompt = f"""
        You are a Senior HR Data Analyst. Analyze the following HR data summary and identify key risks.
        
        ### KPI Summary:
        - Total Headcount: {kpis.get('headcount')}
        - Attrition Rate: {kpis.get('attrition_rate')}%
        - Average Age: {kpis.get('average_age')}
        - Average Tenure: {kpis.get('average_tenure')} years
        
        ### Detected Data Anomalies:
        {issues_str}
        
        ### Task:
        1. Summarize the overall health of the HR data.
        2. Identify the top 3 critical risks (e.g., data entry errors, high attrition, or outlier demographics).
        3. Provide 3-5 actionable recommendations for the HR department.
        
        Format your response in professional business English using Markdown.
        """
        return prompt

if __name__ == "__main__":
    # Test block (Note: will fail without API key)
    detector = AnomalyDetector()
    dummy_issues = [{'issue_type': 'Unrealistic Age', 'value': 150, 'severity': 'High', 'employee_id': 'EMP-1001'}]
    dummy_kpis = {'headcount': 500, 'attrition_rate': 15.2, 'average_age': 35.5, 'average_tenure': 4.2}
    print(detector.analyze_issues(dummy_issues, dummy_kpis))
