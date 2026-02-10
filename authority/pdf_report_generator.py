"""
PDF Business Case Report Generator
Exports impact estimation results to professional PDF reports
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.barcharts import VerticalBarChart
from datetime import datetime
from typing import Dict, Any, List
import io
import logging
logger = logging.getLogger(__name__)



class BusinessCaseReportGenerator:
    """Generate professional PDF reports for business case analysis"""
    
    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self) -> None:
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=12
        ))
        
        self.styles.add(ParagraphStyle(
            name='Highlight',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#27ae60'),
            fontName='Helvetica-Bold'
        ))
    
    def generate_report(
        self,
        use_case: Dict[str, Any],
        assumptions: Dict[str, Any],
        impact: Dict[str, Any],
        sensitivity: Dict[str, Any],
        monte_carlo: Dict[str, Any],
        output_path: str
    ) -> str:
        """Generate complete business case PDF report"""
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )
        
        story = []
        
        # Title Page
        story.extend(self._create_title_page(use_case))
        story.append(PageBreak())
        
        # Executive Summary
        story.extend(self._create_executive_summary(impact, monte_carlo))
        story.append(PageBreak())
        
        # Assumptions
        story.extend(self._create_assumptions_section(assumptions))
        story.append(Spacer(1, 0.3*inch))
        
        # Financial Impact
        story.extend(self._create_financial_impact(impact))
        story.append(PageBreak())
        
        # Year-by-Year Projections
        story.extend(self._create_projections_table(impact["yearly_projections"]))
        story.append(Spacer(1, 0.3*inch))
        
        # Sensitivity Analysis
        story.extend(self._create_sensitivity_section(sensitivity))
        story.append(PageBreak())
        
        # Risk Analysis (Monte Carlo)
        story.extend(self._create_risk_analysis(monte_carlo))
        story.append(Spacer(1, 0.3*inch))
        
        # Recommendations
        story.extend(self._create_recommendations(impact, monte_carlo))
        
        # Build PDF
        doc.build(story)
        
        return output_path
    
    def _create_title_page(self, use_case: Dict[str, Any]) -> List:
        """Create title page"""
        elements = []
        
        # Title
        title = Paragraph(
            "Business Case Analysis",
            self.styles['CustomTitle']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.5*inch))
        
        # Use case name
        use_case_title = Paragraph(
            f"<b>{use_case.get('title', 'OCX Implementation')}</b>",
            self.styles['Heading2']
        )
        elements.append(use_case_title)
        elements.append(Spacer(1, 0.3*inch))
        
        # Description
        description = Paragraph(
            use_case.get('description', ''),
            self.styles['Normal']
        )
        elements.append(description)
        elements.append(Spacer(1, 1*inch))
        
        # Date
        date_text = Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y')}",
            self.styles['Normal']
        )
        elements.append(date_text)
        
        return elements
    
    def _create_executive_summary(self, impact: Dict[str, Any], monte_carlo: Dict[str, Any]) -> List:
        """Create executive summary"""
        elements = []
        
        elements.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        # Key metrics
        roi = impact["three_year_roi"]
        payback = impact["payback_period_years"]
        annual_benefits = impact["total_annual_benefits"]
        
        summary_text = f"""
        <b>3-Year ROI:</b> {roi:.1f}%<br/>
        <b>Payback Period:</b> {payback if payback else 'N/A'} years<br/>
        <b>Annual Benefits:</b> ${annual_benefits:,.0f}<br/>
        <b>Implementation Cost:</b> ${impact['implementation_cost']:,.0f}<br/>
        """
        
        elements.append(Paragraph(summary_text, self.styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))
        
        # Risk assessment
        if monte_carlo:
            prob_positive = monte_carlo["roi"]["probability_positive"] * 100
            
            risk_text = f"""
            <b>Risk Assessment (Monte Carlo Simulation):</b><br/>
            • Probability of Positive ROI: {prob_positive:.1f}%<br/>
            • Expected ROI Range: {monte_carlo['roi']['p25']:.1f}% to {monte_carlo['roi']['p75']:.1f}%<br/>
            • Best Case: {monte_carlo['roi']['max']:.1f}%<br/>
            • Worst Case: {monte_carlo['roi']['min']:.1f}%<br/>
            """
            
            elements.append(Paragraph(risk_text, self.styles['Normal']))
        
        return elements
    
    def _create_assumptions_section(self, assumptions: Dict[str, Any]) -> List:
        """Create assumptions section"""
        elements = []
        
        elements.append(Paragraph("Key Assumptions", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        # Create table of assumptions
        data = [
            ["Assumption", "Value"],
            ["Time Saved per Transaction", f"{assumptions.get('avg_time_saved_per_transaction_minutes', 0):.1f} minutes"],
            ["Transactions per Day", f"{assumptions.get('transactions_per_day', 0):,}"],
            ["Working Days per Year", f"{assumptions.get('working_days_per_year', 0):,}"],
            ["Hourly Labor Cost", f"${assumptions.get('hourly_labor_cost', 0):.2f}"],
            ["Current Error Rate", f"{assumptions.get('current_error_rate', 0)*100:.1f}%"],
            ["Target Error Rate", f"{assumptions.get('target_error_rate', 0)*100:.1f}%"],
            ["Cost per Error", f"${assumptions.get('avg_cost_per_error', 0):,.0f}"],
            ["Current Trust Level", f"{assumptions.get('current_trust_level', 0):.2f}"],
            ["Target Trust Level", f"{assumptions.get('target_trust_level', 0):.2f}"],
        ]
        
        table = Table(data, colWidths=[4*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_financial_impact(self, impact: Dict[str, Any]) -> List:
        """Create financial impact section"""
        elements = []
        
        elements.append(Paragraph("Financial Impact Analysis", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        # Benefits breakdown
        data = [
            ["Benefit Category", "Annual Value"],
            ["Labor Savings", f"${impact['annual_labor_savings']:,.0f}"],
            ["Error Reduction", f"${impact['annual_error_savings']:,.0f}"],
            ["Trust Tax Savings", f"${impact['annual_tax_savings']:,.0f}"],
            ["Total Annual Benefits", f"${impact['total_annual_benefits']:,.0f}"],
        ]
        
        table = Table(data, colWidths=[4*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_projections_table(self, projections: List[Dict[str, Any]]) -> List:
        """Create year-by-year projections table"""
        elements = []
        
        elements.append(Paragraph("3-Year Financial Projections", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        data = [["Year", "Adoption", "Benefits", "Costs", "Net Benefit", "ROI"]]
        
        for proj in projections:
            data.append([
                f"Year {proj['year']}",
                f"{proj['adoption_rate']*100:.0f}%",
                f"${proj['benefits']:,.0f}",
                f"${proj['costs']:,.0f}",
                f"${proj['net_benefit']:,.0f}",
                f"{proj['roi']:.1f}%"
            ])
        
        table = Table(data, colWidths=[1*inch, 1*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_sensitivity_section(self, sensitivity: Dict[str, Any]) -> List:
        """Create sensitivity analysis section"""
        elements = []
        
        elements.append(Paragraph("Sensitivity Analysis", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        elements.append(Paragraph(
            "This analysis shows how changes in key assumptions affect the ROI:",
            self.styles['Normal']
        ))
        elements.append(Spacer(1, 0.2*inch))
        
        # Create table
        data = [["Variable", "Impact", "Low ROI", "Base ROI", "High ROI"]]
        
        for var_name, var_data in sensitivity.items():
            scenarios = var_data["scenarios"]
            data.append([
                var_name.replace('_', ' ').title(),
                var_data["impact"].upper(),
                f"{scenarios['low']['roi']:.1f}%",
                f"{scenarios['base']['roi']:.1f}%",
                f"{scenarios['high']['roi']:.1f}%"
            ])
        
        table = Table(data, colWidths=[2.5*inch, 1*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fadbd8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_risk_analysis(self, monte_carlo: Dict[str, Any]) -> List:
        """Create risk analysis section"""
        elements = []
        
        elements.append(Paragraph("Risk Analysis (Monte Carlo Simulation)", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        roi_stats = monte_carlo["roi"]
        
        text = f"""
        Based on {monte_carlo['num_iterations']:,} simulations:<br/><br/>
        
        <b>ROI Distribution:</b><br/>
        • Mean: {roi_stats['mean']:.1f}%<br/>
        • Median: {roi_stats['median']:.1f}%<br/>
        • Standard Deviation: {roi_stats['std_dev']:.1f}%<br/>
        • 10th Percentile: {roi_stats['p10']:.1f}%<br/>
        • 90th Percentile: {roi_stats['p90']:.1f}%<br/><br/>
        
        <b>Probability of Success:</b><br/>
        • Positive ROI: {roi_stats['probability_positive']*100:.1f}%<br/>
        • Payback within 3 years: {monte_carlo['payback_period']['probability_within_3_years']*100:.1f}%<br/>
        """
        
        elements.append(Paragraph(text, self.styles['Normal']))
        
        return elements
    
    def _create_recommendations(self, impact: Dict[str, Any], monte_carlo: Dict[str, Any]) -> List:
        """Create recommendations section"""
        elements = []
        
        elements.append(Paragraph("Recommendations", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*inch))
        
        roi = impact["three_year_roi"]
        prob_positive = monte_carlo["roi"]["probability_positive"]
        
        if roi > 100 and prob_positive > 0.8:
            recommendation = "STRONG RECOMMENDATION: Proceed with implementation"
            color = colors.HexColor('#27ae60')
        elif roi > 50 and prob_positive > 0.7:
            recommendation = "RECOMMENDATION: Proceed with implementation"
            color = colors.HexColor('#f39c12')
        elif roi > 0 and prob_positive > 0.6:
            recommendation = "CONDITIONAL: Consider pilot program first"
            color = colors.HexColor('#e67e22')
        else:
            recommendation = "CAUTION: Reassess assumptions and risks"
            color = colors.HexColor('#e74c3c')
        
        rec_style = ParagraphStyle(
            name='Recommendation',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=color,
            fontName='Helvetica-Bold'
        )
        
        elements.append(Paragraph(recommendation, rec_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Next steps
        next_steps = """
        <b>Suggested Next Steps:</b><br/>
        1. Review and validate all assumptions with stakeholders<br/>
        2. Conduct pilot program with select use cases<br/>
        3. Establish success metrics and monitoring<br/>
        4. Plan phased rollout based on adoption rates<br/>
        5. Schedule quarterly reviews to track actual vs. projected benefits<br/>
        """
        
        elements.append(Paragraph(next_steps, self.styles['Normal']))
        
        return elements
