"""Report generation module."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .models import Report, ReportConfig, ReportFormat, ReportSection

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Automated report generator."""

    def __init__(self, output_dir: str = "./data/reports"):
        """Initialize report generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self, sections: List[ReportSection], config: ReportConfig
    ) -> Report:
        """Generate report.

        Args:
            sections: Report sections
            config: Report configuration

        Returns:
            Generated Report object
        """
        report_id = f"report_{uuid.uuid4().hex[:8]}"

        # Generate report based on format
        if config.format == ReportFormat.HTML:
            file_path = self._generate_html_report(report_id, sections, config)
        elif config.format == ReportFormat.MARKDOWN:
            file_path = self._generate_markdown_report(report_id, sections, config)
        elif config.format == ReportFormat.JSON:
            file_path = self._generate_json_report(report_id, sections, config)
        elif config.format == ReportFormat.PDF:
            # PDF generation requires additional dependencies (matplotlib, reportlab)
            # For now, generate HTML and note that PDF conversion would be next step
            file_path = self._generate_html_report(report_id, sections, config)
            logger.warning(
                "PDF generation not fully implemented - generating HTML instead"
            )
        else:
            raise ValueError(f"Unsupported report format: {config.format}")

        return Report(
            report_id=report_id,
            config=config,
            sections=sections,
            file_path=str(file_path),
        )

    def _generate_html_report(
        self, report_id: str, sections: List[ReportSection], config: ReportConfig
    ) -> Path:
        """Generate HTML report."""
        output_file = self.output_dir / f"{report_id}.html"

        html = self._build_html_header(config)

        # Add sections
        for section in sections:
            html += f"<h2>{section.title}</h2>\n"
            html += f"<div class='section-content'>\n{section.content}\n</div>\n"

            # Add plots if any
            for plot_path in section.plots:
                html += f"<img src='{plot_path}' alt='{section.title} plot' />\n"

            # Add tables if any
            for table in section.tables:
                html += self._build_html_table(table)

        html += self._build_html_footer()

        output_file.write_text(html)
        logger.info(f"Generated HTML report: {output_file}")

        return output_file

    def _generate_markdown_report(
        self, report_id: str, sections: List[ReportSection], config: ReportConfig
    ) -> Path:
        """Generate Markdown report."""
        output_file = self.output_dir / f"{report_id}.md"

        md = f"# {config.title}\n\n"
        md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        if config.author:
            md += f"**Author**: {config.author}\n\n"

        # Add sections
        for section in sections:
            md += f"## {section.title}\n\n"
            md += f"{section.content}\n\n"

            # Add plots
            for plot_path in section.plots:
                md += f"![{section.title}]({plot_path})\n\n"

            # Add tables
            for table in section.tables:
                md += self._build_markdown_table(table)

        output_file.write_text(md)
        logger.info(f"Generated Markdown report: {output_file}")

        return output_file

    def _generate_json_report(
        self, report_id: str, sections: List[ReportSection], config: ReportConfig
    ) -> Path:
        """Generate JSON report."""
        output_file = self.output_dir / f"{report_id}.json"

        report_data = {
            "report_id": report_id,
            "title": config.title,
            "generated": datetime.now().isoformat(),
            "author": config.author,
            "company": config.company,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "plots": s.plots,
                    "tables": s.tables,
                }
                for s in sections
            ],
        }

        output_file.write_text(json.dumps(report_data, indent=2))
        logger.info(f"Generated JSON report: {output_file}")

        return output_file

    def _build_html_header(self, config: ReportConfig) -> str:
        """Build HTML header."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{config.title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        h1 {{
            margin: 0;
        }}
        h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 5px;
        }}
        .section-content {{
            background-color: white;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        img {{
            max-width: 100%;
            height: auto;
            margin: 10px 0;
        }}
        .footer {{
            text-align: center;
            color: #7f8c8d;
            margin-top: 30px;
            padding: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{config.title}</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""
        if config.author:
            html += f"        <p>Author: {config.author}</p>\n"
        if config.company:
            html += f"        <p>Company: {config.company}</p>\n"

        html += "    </div>\n"

        return html

    def _build_html_footer(self) -> str:
        """Build HTML footer."""
        return """
    <div class="footer">
        <p>Generated by LabLink Analysis System</p>
    </div>
</body>
</html>
"""

    def _build_html_table(self, table: Dict[str, Any]) -> str:
        """Build HTML table from data."""
        if not table:
            return ""

        html = "<table>\n"

        # Header row
        headers = list(table.keys())
        html += "  <tr>\n"
        for header in headers:
            html += f"    <th>{header}</th>\n"
        html += "  </tr>\n"

        # Data rows
        num_rows = len(table[headers[0]]) if isinstance(table[headers[0]], list) else 1

        for i in range(num_rows):
            html += "  <tr>\n"
            for header in headers:
                value = (
                    table[header][i]
                    if isinstance(table[header], list)
                    else table[header]
                )
                html += f"    <td>{value}</td>\n"
            html += "  </tr>\n"

        html += "</table>\n"

        return html

    def _build_markdown_table(self, table: Dict[str, Any]) -> str:
        """Build Markdown table from data."""
        if not table:
            return ""

        headers = list(table.keys())
        md = "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join(["---"] * len(headers)) + " |\n"

        # Data rows
        num_rows = len(table[headers[0]]) if isinstance(table[headers[0]], list) else 1

        for i in range(num_rows):
            row_values = []
            for header in headers:
                value = (
                    table[header][i]
                    if isinstance(table[header], list)
                    else table[header]
                )
                row_values.append(str(value))
            md += "| " + " | ".join(row_values) + " |\n"

        md += "\n"

        return md

    def create_section(
        self,
        title: str,
        content: str,
        plots: List[str] = None,
        tables: List[Dict[str, Any]] = None,
    ) -> ReportSection:
        """Create a report section.

        Args:
            title: Section title
            content: Section content (text/HTML)
            plots: List of plot file paths
            tables: List of data tables

        Returns:
            ReportSection object
        """
        return ReportSection(
            title=title,
            content=content,
            plots=plots or [],
            tables=tables or [],
        )
