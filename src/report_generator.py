import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    Generates professional PDF reports summarized from HR data analysis.
    """
    
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_pdf(self, kpis: Dict[str, Any], ai_insights: str) -> str:
        """
        Creates a PDF report and returns the file path.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"HR_Analysis_Report_{timestamp}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        
        logger.info(f"Generating PDF report: {filepath}")
        
        c = canvas.Canvas(filepath, pagesize=LETTER)
        width, height = LETTER

        # Title
        c.setFont("Helvetica-Bold", 20)
        c.drawString(100, height - 50, "Human Capital Dashboard Analysis Report")
        
        c.setFont("Helvetica", 10)
        c.drawString(100, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # KPI Section
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, height - 110, "1. KPI Summary")
        
        c.setFont("Helvetica", 12)
        y = height - 130
        c.drawString(120, y, f"- Total Headcount: {kpis.get('headcount')}")
        y -= 20
        c.drawString(120, y, f"- Attrition Rate: {kpis.get('attrition_rate')}%")
        y -= 20
        c.drawString(120, y, f"- Average Age: {kpis.get('average_age')}")
        y -= 20
        c.drawString(120, y, f"- Average Tenure: {kpis.get('average_tenure')} years")
        
        # AI Insights Section
        c.setFont("Helvetica-Bold", 14)
        y -= 40
        c.drawString(100, y, "2. AI-Driven Insights & Recommendations")
        
        c.setFont("Helvetica", 10)
        y -= 20
        
        # Simple text wrapping for AI insights
        text_object = c.beginText(100, y)
        text_object.setFont("Helvetica", 10)
        text_object.setLeading(14)
        
        lines = ai_insights.split('\n')
        for line in lines:
            # Wrap basic text (simplistic)
            if len(line) > 90:
                text_object.textLine(line[:90])
                text_object.textLine(line[90:])
            else:
                text_object.textLine(line)
        
        c.drawText(text_object)
        
        c.showPage()
        c.save()
        
        logger.info("PDF report generation complete.")
        return filepath

if __name__ == "__main__":
    # Test block
    gen = ReportGenerator()
    dummy_kpis = {'headcount': 500, 'attrition_rate': 12.5, 'average_age': 38.2, 'average_tenure': 5.1}
    dummy_ai = "Overall health looks good. Risk of high attrition in Sales. Recommend retention bonus."
    print(f"Report saved to: {gen.generate_pdf(dummy_kpis, dummy_ai)}")
