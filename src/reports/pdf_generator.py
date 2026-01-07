#!/usr/bin/env python3
"""
PDF Report Generator for PII Analyzer

Generates comprehensive PDF reports including:
- Executive Summary
- Statistics breakdown
- High-risk file listings
- Entity type analysis
- Detailed per-file findings
"""

import os
import sys
import io
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database.db_utils import get_database
from src.database.db_reporting import (
    get_file_processing_stats,
    get_file_type_statistics,
    get_entity_statistics
)

logger = logging.getLogger('pdf_generator')

# Entity display names mapping
ENTITY_DISPLAY_NAMES = {
    'US_SSN': 'Social Security Number',
    'CREDIT_CARD': 'Credit Card Number',
    'EMAIL_ADDRESS': 'Email Address',
    'PHONE_NUMBER': 'Phone Number',
    'PERSON': 'Person Name',
    'LOCATION': 'Location/Address',
    'DATE_TIME': 'Date/Time',
    'IP_ADDRESS': 'IP Address',
    'US_DRIVER_LICENSE': 'Driver License',
    'US_PASSPORT': 'Passport Number',
    'US_BANK_NUMBER': 'Bank Account Number',
    'IBAN_CODE': 'IBAN Code',
    'NRP': 'National ID',
    'MEDICAL_LICENSE': 'Medical License',
    'URL': 'URL',
}


class PIIReportGenerator:
    """Generate PDF reports for PII analysis results"""
    
    def __init__(self, db_path: str, job_id: Optional[int] = None):
        """
        Initialize the report generator
        
        Args:
            db_path: Path to the SQLite database
            job_id: Specific job ID (uses most recent if None)
        """
        self.db_path = db_path
        self.db = get_database(db_path)
        
        # Get job ID
        if job_id is None:
            jobs = self.db.get_all_jobs()
            if not jobs:
                raise ValueError("No jobs found in database")
            self.job_id = jobs[0]['job_id']
        else:
            self.job_id = job_id
        
        # Get job info
        self.job = self.db.get_job(self.job_id)
        if not self.job:
            raise ValueError(f"Job {self.job_id} not found")
        
        # Set up styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Set up custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1a365d')
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=12,
            textColor=colors.HexColor('#2c5282')
        ))
        
        self.styles.add(ParagraphStyle(
            name='SubsectionTitle',
            parent=self.styles['Heading3'],
            fontSize=12,
            spaceBefore=12,
            spaceAfter=8,
            textColor=colors.HexColor('#2b6cb0')
        ))
        
        self.styles.add(ParagraphStyle(
            name='BodyTextIndent',
            parent=self.styles['Normal'],
            leftIndent=20,
            spaceAfter=6
        ))
        
        self.styles.add(ParagraphStyle(
            name='HighRiskItem',
            parent=self.styles['Normal'],
            fontSize=9,
            leftIndent=10,
            textColor=colors.HexColor('#c53030')
        ))
        
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.gray,
            alignment=TA_CENTER
        ))
    
    def generate_report(self, output_path: Optional[str] = None) -> bytes:
        """
        Generate the PDF report
        
        Args:
            output_path: Optional file path to save the PDF
            
        Returns:
            PDF content as bytes
        """
        # Create buffer for PDF
        buffer = io.BytesIO()
        
        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Build content
        story = []
        
        # Title page
        story.extend(self._build_title_page())
        story.append(PageBreak())
        
        # Executive Summary
        story.extend(self._build_executive_summary())
        story.append(PageBreak())
        
        # Statistics Overview
        story.extend(self._build_statistics_section())
        story.append(PageBreak())
        
        # Entity Analysis
        story.extend(self._build_entity_analysis())
        story.append(PageBreak())
        
        # High Risk Files (with full paths)
        story.extend(self._build_high_risk_files())
        story.append(PageBreak())
        
        # All Files with PII (complete listing with full paths)
        story.extend(self._build_all_pii_files())
        story.append(PageBreak())
        
        # Detailed Findings (sample)
        story.extend(self._build_detailed_findings())
        
        # Build PDF
        doc.build(story, onFirstPage=self._add_page_number, onLaterPages=self._add_page_number)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Optionally save to file
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(pdf_content)
            logger.info(f"Report saved to: {output_path}")
        
        return pdf_content
    
    def _add_page_number(self, canvas, doc):
        """Add page number to each page"""
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.gray)
        canvas.drawCentredString(letter[0]/2, 0.5*inch, text)
        canvas.restoreState()
    
    def _build_title_page(self) -> List:
        """Build the title page"""
        elements = []
        
        # Add some space at top
        elements.append(Spacer(1, 2*inch))
        
        # Title
        elements.append(Paragraph("PII Analysis Report", self.styles['ReportTitle']))
        elements.append(Spacer(1, 0.5*inch))
        
        # Subtitle with directory
        directory = self.job.get('directory', 'Unknown')
        elements.append(Paragraph(
            f"Analysis of: {directory}",
            ParagraphStyle(
                'Subtitle',
                parent=self.styles['Normal'],
                fontSize=14,
                alignment=TA_CENTER,
                textColor=colors.HexColor('#4a5568')
            )
        ))
        
        elements.append(Spacer(1, inch))
        
        # Report metadata
        metadata_style = ParagraphStyle(
            'Metadata',
            parent=self.styles['Normal'],
            fontSize=11,
            alignment=TA_CENTER,
            spaceAfter=6
        )
        
        elements.append(Paragraph(
            f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            metadata_style
        ))
        elements.append(Paragraph(
            f"<b>Job ID:</b> {self.job_id}",
            metadata_style
        ))
        elements.append(Paragraph(
            f"<b>Job Status:</b> {self.job.get('status', 'Unknown')}",
            metadata_style
        ))
        
        # Get processing stats for summary
        stats = get_file_processing_stats(self.db_path, self.job_id)
        elements.append(Spacer(1, 0.5*inch))
        elements.append(Paragraph(
            f"<b>Total Files Analyzed:</b> {stats.get('total_registered', 0):,}",
            metadata_style
        ))
        
        return elements
    
    def _build_executive_summary(self) -> List:
        """Build the executive summary section"""
        elements = []
        
        elements.append(Paragraph("Executive Summary", self.styles['SectionTitle']))
        elements.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0')))
        elements.append(Spacer(1, 12))
        
        # Get statistics
        stats = get_file_processing_stats(self.db_path, self.job_id)
        entity_stats = get_entity_statistics(self.db_path, self.job_id)
        
        total_files = stats.get('total_registered', 0)
        completed = stats.get('completed', 0)
        errors = stats.get('error', 0)
        total_entities = sum(entity_stats.values())
        
        # Summary paragraph
        summary_text = f"""
        This report summarizes the results of a PII (Personally Identifiable Information) analysis 
        conducted on <b>{total_files:,}</b> files. The analysis successfully processed 
        <b>{completed:,}</b> files and identified <b>{total_entities:,}</b> potential PII instances 
        across <b>{len(entity_stats)}</b> different entity types.
        """
        elements.append(Paragraph(summary_text, self.styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Key findings table
        elements.append(Paragraph("Key Findings", self.styles['SubsectionTitle']))
        
        # Get high risk files count (files with SSN or Credit Card)
        high_risk_entities = ['US_SSN', 'CREDIT_CARD', 'US_DRIVER_LICENSE', 'US_PASSPORT']
        high_risk_count = sum(entity_stats.get(e, 0) for e in high_risk_entities)
        
        findings_data = [
            ['Metric', 'Value'],
            ['Total Files Scanned', f'{total_files:,}'],
            ['Files Successfully Processed', f'{completed:,}'],
            ['Files with Errors', f'{errors:,}'],
            ['Total PII Instances Found', f'{total_entities:,}'],
            ['High-Risk PII (SSN, CC, DL, Passport)', f'{high_risk_count:,}'],
            ['Unique Entity Types Detected', f'{len(entity_stats)}'],
        ]
        
        findings_table = Table(findings_data, colWidths=[3*inch, 2*inch])
        findings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(findings_table)
        
        elements.append(Spacer(1, 24))
        
        # Risk Assessment
        elements.append(Paragraph("Risk Assessment", self.styles['SubsectionTitle']))
        
        if high_risk_count > 0:
            risk_text = f"""
            <font color="#c53030"><b>HIGH RISK:</b></font> This analysis identified {high_risk_count:,} instances 
            of high-risk PII including Social Security Numbers, Credit Card Numbers, Driver's License Numbers, 
            and Passport Numbers. Immediate review and remediation is recommended.
            """
        elif total_entities > 0:
            risk_text = f"""
            <font color="#dd6b20"><b>MODERATE RISK:</b></font> This analysis identified {total_entities:,} instances 
            of PII. While no high-risk identifiers (SSN, Credit Cards) were found, the detected PII should be 
            reviewed to ensure proper handling.
            """
        else:
            risk_text = """
            <font color="#38a169"><b>LOW RISK:</b></font> No PII was detected in this analysis. 
            However, manual review of sampled files is still recommended.
            """
        
        elements.append(Paragraph(risk_text, self.styles['Normal']))
        
        return elements
    
    def _build_statistics_section(self) -> List:
        """Build the statistics overview section"""
        elements = []
        
        elements.append(Paragraph("Processing Statistics", self.styles['SectionTitle']))
        elements.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0')))
        elements.append(Spacer(1, 12))
        
        # File processing stats
        stats = get_file_processing_stats(self.db_path, self.job_id)
        
        elements.append(Paragraph("File Processing Summary", self.styles['SubsectionTitle']))
        
        processing_data = [
            ['Status', 'Count', 'Percentage'],
            ['Completed', f"{stats.get('completed', 0):,}", 
             f"{stats.get('completed', 0) / max(stats.get('total_registered', 1), 1) * 100:.1f}%"],
            ['Pending', f"{stats.get('pending', 0):,}",
             f"{stats.get('pending', 0) / max(stats.get('total_registered', 1), 1) * 100:.1f}%"],
            ['Processing', f"{stats.get('processing', 0):,}",
             f"{stats.get('processing', 0) / max(stats.get('total_registered', 1), 1) * 100:.1f}%"],
            ['Error', f"{stats.get('error', 0):,}",
             f"{stats.get('error', 0) / max(stats.get('total_registered', 1), 1) * 100:.1f}%"],
        ]
        
        processing_table = Table(processing_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
        processing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(processing_table)
        
        elements.append(Spacer(1, 24))
        
        # File type breakdown
        elements.append(Paragraph("File Type Distribution", self.styles['SubsectionTitle']))
        
        file_types = get_file_type_statistics(self.db_path, self.job_id)
        total_files = sum(file_types.values())
        
        # Sort and limit to top 15
        sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:15]
        
        type_data = [['File Type', 'Count', 'Percentage']]
        for file_type, count in sorted_types:
            type_data.append([
                file_type or 'Unknown',
                f"{count:,}",
                f"{count / max(total_files, 1) * 100:.1f}%"
            ])
        
        type_table = Table(type_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        type_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(type_table)
        
        return elements
    
    def _build_entity_analysis(self) -> List:
        """Build the entity analysis section"""
        elements = []
        
        elements.append(Paragraph("PII Entity Analysis", self.styles['SectionTitle']))
        elements.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0')))
        elements.append(Spacer(1, 12))
        
        entity_stats = get_entity_statistics(self.db_path, self.job_id)
        total_entities = sum(entity_stats.values())
        
        if not entity_stats:
            elements.append(Paragraph(
                "No PII entities were detected in the analyzed files.",
                self.styles['Normal']
            ))
            return elements
        
        elements.append(Paragraph(
            f"A total of <b>{total_entities:,}</b> PII instances were detected across "
            f"<b>{len(entity_stats)}</b> different entity types.",
            self.styles['Normal']
        ))
        elements.append(Spacer(1, 12))
        
        # Entity breakdown table
        elements.append(Paragraph("Entity Type Breakdown", self.styles['SubsectionTitle']))
        
        sorted_entities = sorted(entity_stats.items(), key=lambda x: x[1], reverse=True)
        
        entity_data = [['Entity Type', 'Description', 'Count', '%']]
        for entity_type, count in sorted_entities:
            display_name = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)
            entity_data.append([
                entity_type,
                display_name,
                f"{count:,}",
                f"{count / max(total_entities, 1) * 100:.1f}%"
            ])
        
        entity_table = Table(entity_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 0.75*inch])
        entity_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(entity_table)
        
        elements.append(Spacer(1, 24))
        
        # High-risk entities callout
        high_risk_types = ['US_SSN', 'CREDIT_CARD', 'US_DRIVER_LICENSE', 'US_PASSPORT', 'US_BANK_NUMBER']
        high_risk_found = {k: v for k, v in entity_stats.items() if k in high_risk_types and v > 0}
        
        if high_risk_found:
            elements.append(Paragraph("⚠️ High-Risk PII Detected", self.styles['SubsectionTitle']))
            
            alert_text = "The following high-risk PII types require immediate attention:"
            elements.append(Paragraph(alert_text, self.styles['Normal']))
            elements.append(Spacer(1, 8))
            
            for entity_type, count in sorted(high_risk_found.items(), key=lambda x: x[1], reverse=True):
                display_name = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)
                elements.append(Paragraph(
                    f"• <b>{display_name}</b>: {count:,} instances",
                    self.styles['HighRiskItem']
                ))
        
        return elements
    
    def _build_high_risk_files(self) -> List:
        """Build the high-risk files section"""
        elements = []
        
        elements.append(Paragraph("High-Risk Files", self.styles['SectionTitle']))
        elements.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0')))
        elements.append(Spacer(1, 12))
        
        # Query files with high-risk PII
        try:
            cursor = self.db.conn.cursor()
            
            # Get files with SSN, Credit Card, DL, or Passport
            query = """
                SELECT DISTINCT f.file_path, GROUP_CONCAT(DISTINCT e.entity_type) as entity_types,
                       COUNT(e.entity_id) as entity_count
                FROM files f
                JOIN entities e ON f.file_id = e.file_id
                WHERE f.job_id = ?
                  AND e.entity_type IN ('US_SSN', 'CREDIT_CARD', 'US_DRIVER_LICENSE', 'US_PASSPORT', 'US_BANK_NUMBER')
                GROUP BY f.file_id
                ORDER BY entity_count DESC
            """
            cursor.execute(query, (self.job_id,))
            high_risk_files = cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error querying high-risk files: {e}")
            high_risk_files = []
        
        if not high_risk_files:
            elements.append(Paragraph(
                "No high-risk files (containing SSN, Credit Card, DL, or Passport numbers) were identified.",
                self.styles['Normal']
            ))
            return elements
        
        elements.append(Paragraph(
            f"<b>{len(high_risk_files)}</b> files were identified as high-risk, "
            "containing sensitive PII such as Social Security Numbers, Credit Card Numbers, "
            "Driver's License Numbers, or Passport Numbers.",
            self.styles['Normal']
        ))
        elements.append(Spacer(1, 12))
        
        # Summary table with counts by PII type
        elements.append(Paragraph("High-Risk PII Summary by Type", self.styles['SubsectionTitle']))
        
        # Create summary
        type_counts = {}
        for _, entity_types, count in high_risk_files:
            if entity_types:
                for et in entity_types.split(','):
                    et = et.strip()
                    display_name = ENTITY_DISPLAY_NAMES.get(et, et)
                    type_counts[display_name] = type_counts.get(display_name, 0) + 1
        
        summary_data = [['PII Type', 'Files Affected']]
        for pii_type, file_count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            summary_data.append([pii_type, str(file_count)])
        
        summary_table = Table(summary_data, colWidths=[3*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c53030')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#fff5f5'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#feb2b2')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 16))
        
        # Full file listing with complete paths
        elements.append(Paragraph("Complete High-Risk File Listing", self.styles['SubsectionTitle']))
        elements.append(Spacer(1, 8))
        
        # List all high-risk files with full paths
        for i, (file_path, entity_types, count) in enumerate(high_risk_files, 1):
            # Format entity types for display
            if entity_types:
                formatted_types = ', '.join([
                    ENTITY_DISPLAY_NAMES.get(et.strip(), et.strip()) 
                    for et in entity_types.split(',')
                ])
            else:
                formatted_types = 'Unknown'
            
            # Create a paragraph for each file with full path
            file_entry = f"<b>{i}.</b> {file_path}<br/>" \
                        f"<font size='8' color='#666666'>    PII Types: {formatted_types} | Count: {count}</font>"
            elements.append(Paragraph(file_entry, self.styles['HighRiskItem']))
            elements.append(Spacer(1, 4))
            
            # Add page break every 40 files to avoid memory issues with very long lists
            if i > 0 and i % 40 == 0 and i < len(high_risk_files):
                elements.append(PageBreak())
                elements.append(Paragraph(
                    f"High-Risk Files (continued - {i+1} to {min(i+40, len(high_risk_files))})", 
                    self.styles['SubsectionTitle']
                ))
                elements.append(Spacer(1, 8))
        
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            f"<b>Total High-Risk Files: {len(high_risk_files)}</b>",
            self.styles['Normal']
        ))
        
        return elements
    
    def _build_all_pii_files(self) -> List:
        """Build a section listing ALL files with any PII detected"""
        elements = []
        
        elements.append(Paragraph("All Files with PII Detected", self.styles['SectionTitle']))
        elements.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0')))
        elements.append(Spacer(1, 12))
        
        # Query all files with any PII
        try:
            cursor = self.db.conn.cursor()
            
            query = """
                SELECT DISTINCT f.file_path, GROUP_CONCAT(DISTINCT e.entity_type) as entity_types,
                       COUNT(e.entity_id) as entity_count
                FROM files f
                JOIN entities e ON f.file_id = e.file_id
                WHERE f.job_id = ?
                GROUP BY f.file_id
                ORDER BY entity_count DESC
            """
            cursor.execute(query, (self.job_id,))
            all_pii_files = cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error querying all PII files: {e}")
            all_pii_files = []
        
        if not all_pii_files:
            elements.append(Paragraph(
                "No files with PII were detected in this analysis.",
                self.styles['Normal']
            ))
            return elements
        
        elements.append(Paragraph(
            f"<b>{len(all_pii_files)}</b> files were found containing PII of any type.",
            self.styles['Normal']
        ))
        elements.append(Spacer(1, 12))
        
        # List all files with full paths
        for i, (file_path, entity_types, count) in enumerate(all_pii_files, 1):
            # Format entity types for display
            if entity_types:
                formatted_types = ', '.join([
                    ENTITY_DISPLAY_NAMES.get(et.strip(), et.strip()) 
                    for et in entity_types.split(',')
                ])
            else:
                formatted_types = 'Unknown'
            
            # Determine risk level for color coding
            high_risk_types = ['US_SSN', 'CREDIT_CARD', 'US_DRIVER_LICENSE', 'US_PASSPORT', 'US_BANK_NUMBER']
            is_high_risk = any(et.strip() in high_risk_types for et in (entity_types or '').split(','))
            
            if is_high_risk:
                color = '#c53030'  # Red for high-risk
                risk_label = '[HIGH RISK] '
            else:
                color = '#2b6cb0'  # Blue for standard PII
                risk_label = ''
            
            # Create a paragraph for each file with full path
            file_entry = f"<b>{i}.</b> <font color='{color}'>{risk_label}</font>{file_path}<br/>" \
                        f"<font size='8' color='#666666'>    PII Types: {formatted_types} | Count: {count}</font>"
            elements.append(Paragraph(file_entry, self.styles['BodyTextIndent']))
            elements.append(Spacer(1, 4))
            
            # Add page break every 40 files
            if i > 0 and i % 40 == 0 and i < len(all_pii_files):
                elements.append(PageBreak())
                elements.append(Paragraph(
                    f"All Files with PII (continued - {i+1} to {min(i+40, len(all_pii_files))})", 
                    self.styles['SubsectionTitle']
                ))
                elements.append(Spacer(1, 8))
        
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            f"<b>Total Files with PII: {len(all_pii_files)}</b>",
            self.styles['Normal']
        ))
        
        return elements
    
    def _build_detailed_findings(self) -> List:
        """Build detailed findings section with sample entries"""
        elements = []
        
        elements.append(Paragraph("Detailed Findings Sample", self.styles['SectionTitle']))
        elements.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0')))
        elements.append(Spacer(1, 12))
        
        elements.append(Paragraph(
            "This section provides a sample of detailed PII findings. For complete results, "
            "please export the full JSON report.",
            self.styles['Normal']
        ))
        elements.append(Spacer(1, 12))
        
        # Get sample files with entities
        try:
            cursor = self.db.conn.cursor()
            
            # Get 10 sample files with their entities
            query = """
                SELECT f.file_path, e.entity_type, e.text, e.score, e.start_pos, e.end_pos
                FROM files f
                JOIN entities e ON f.file_id = e.file_id
                WHERE f.job_id = ?
                ORDER BY e.score DESC
                LIMIT 100
            """
            cursor.execute(query, (self.job_id,))
            findings = cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error querying detailed findings: {e}")
            findings = []
        
        if not findings:
            elements.append(Paragraph(
                "No detailed findings available.",
                self.styles['Normal']
            ))
            return elements
        
        # Group by file
        files_dict = {}
        for file_path, entity_type, text, score, start, end in findings:
            if file_path not in files_dict:
                files_dict[file_path] = []
            # Mask the detected text for security
            masked_text = text[:2] + '*' * (len(text) - 4) + text[-2:] if len(text) > 4 else '*' * len(text)
            files_dict[file_path].append({
                'type': entity_type,
                'text': masked_text,
                'score': score
            })
        
        # Show first 10 files
        for i, (file_path, entities) in enumerate(list(files_dict.items())[:10], 1):
            # File header
            display_path = file_path if len(file_path) <= 70 else '...' + file_path[-67:]
            elements.append(Paragraph(f"<b>File {i}:</b> {display_path}", self.styles['SubsectionTitle']))
            
            # Entities table
            entity_data = [['Entity Type', 'Detected Value (Masked)', 'Confidence']]
            for entity in entities[:5]:  # Limit entities per file
                entity_data.append([
                    entity['type'],
                    entity['text'],
                    f"{entity['score']:.0%}"
                ])
            
            entity_table = Table(entity_data, colWidths=[1.5*inch, 3*inch, 1*inch])
            entity_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#edf2f7'), colors.white]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(entity_table)
            elements.append(Spacer(1, 12))
        
        if len(files_dict) > 10:
            elements.append(Paragraph(
                f"<i>Showing 10 of {len(files_dict)} files with findings.</i>",
                self.styles['Footer']
            ))
        
        return elements


def generate_pdf_report(db_path: str, job_id: Optional[int] = None, output_path: Optional[str] = None) -> bytes:
    """
    Convenience function to generate a PDF report
    
    Args:
        db_path: Path to the SQLite database
        job_id: Specific job ID (uses most recent if None)
        output_path: Optional file path to save the PDF
        
    Returns:
        PDF content as bytes
    """
    generator = PIIReportGenerator(db_path, job_id)
    return generator.generate_report(output_path)

