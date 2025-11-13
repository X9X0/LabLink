#!/bin/bash
# LabLink Log Analysis Examples
# ==============================
#
# This script demonstrates common log analysis tasks using the LabLink log analysis tools.
# You can run individual commands by copying and pasting them.

set -e

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_section() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

echo_command() {
    echo -e "${GREEN}$ $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "log_analyzer.py" ]; then
    echo "Error: Must be run from the server directory"
    exit 1
fi

# ============================================================================
# EXAMPLE 1: Basic Log Queries
# ============================================================================

echo_section "Example 1: Basic Log Queries"

echo_command "python log_analyzer.py query --level ERROR --last 1h"
echo "Description: Find all errors from the last hour"
echo ""

echo_command "python log_analyzer.py query --logger equipment --last 24h --limit 50"
echo "Description: Get last 50 equipment-related log entries from past day"
echo ""

echo_command "python log_analyzer.py query --keyword 'connection' 'failed' --output-format json -o connection_issues.json"
echo "Description: Search for connection failures and save to JSON file"
echo ""

# ============================================================================
# EXAMPLE 2: Generating Reports
# ============================================================================

echo_section "Example 2: Generating Reports"

echo_command "python log_analyzer.py report --type summary"
echo "Description: Generate a high-level summary report"
echo ""

echo_command "python log_analyzer.py report --type errors -o error_report.txt"
echo "Description: Generate detailed error analysis and save to file"
echo ""

echo_command "python log_analyzer.py report --type performance --format json"
echo "Description: Generate performance report in JSON format"
echo ""

# ============================================================================
# EXAMPLE 3: Anomaly Detection
# ============================================================================

echo_section "Example 3: Anomaly Detection"

echo_command "python log_analyzer.py anomaly --sensitivity medium"
echo "Description: Detect anomalies with medium sensitivity"
echo ""

echo_command "python log_analyzer.py anomaly --sensitivity high"
echo "Description: Detect anomalies with high sensitivity (more alerts)"
echo ""

# ============================================================================
# EXAMPLE 4: Real-Time Monitoring
# ============================================================================

echo_section "Example 4: Real-Time Monitoring"

echo_command "python log_monitor.py --follow"
echo "Description: Monitor all logs in real-time"
echo ""

echo_command "python log_monitor.py --follow --level ERROR WARNING"
echo "Description: Monitor only errors and warnings"
echo ""

echo_command "python log_monitor.py --follow --logger equipment --keyword 'PSU_001'"
echo "Description: Monitor specific equipment activity"
echo ""

echo_command "python log_monitor.py --follow --alert-on 'failed' 'timeout' 'critical'"
echo "Description: Monitor with alerts on specific keywords"
echo ""

echo_command "python log_monitor.py --follow --stats-interval 60"
echo "Description: Monitor with statistics displayed every 60 seconds"
echo ""

# ============================================================================
# EXAMPLE 5: Automated Reports
# ============================================================================

echo_section "Example 5: Automated Reports"

echo_command "python generate_log_reports.py --period daily"
echo "Description: Generate daily report (last 24 hours)"
echo ""

echo_command "python generate_log_reports.py --period weekly --format html -o weekly_report.html"
echo "Description: Generate weekly report as HTML"
echo ""

echo_command "python generate_log_reports.py --custom --days 7 --format json -o custom_report.json"
echo "Description: Generate custom 7-day report in JSON format"
echo ""

# ============================================================================
# EXAMPLE 6: Debugging Workflows
# ============================================================================

echo_section "Example 6: Debugging Workflows"

echo "Workflow: Investigating equipment connection issues"
echo ""

echo_command "# Step 1: Find recent connection errors"
echo "python log_analyzer.py query --logger equipment --keyword 'connection' --level ERROR --last 2d"
echo ""

echo_command "# Step 2: Generate error analysis"
echo "python log_analyzer.py report --type errors --file-pattern 'equipment*.log'"
echo ""

echo_command "# Step 3: Monitor for new occurrences"
echo "python log_monitor.py --follow --logger equipment --alert-on 'connection' 'timeout'"
echo ""

# ============================================================================
# EXAMPLE 7: Performance Analysis
# ============================================================================

echo_section "Example 7: Performance Analysis"

echo "Workflow: Analyzing API performance"
echo ""

echo_command "# Step 1: Generate performance baseline"
echo "python log_analyzer.py report --type performance --file-pattern 'access.log' -o baseline.txt"
echo ""

echo_command "# Step 2: Find slow requests (using jq for JSON parsing)"
echo "python log_analyzer.py query --logger access --output-format json | jq '.[] | select(.duration_ms > 1000) | {endpoint: .path, duration: .duration_ms}'"
echo ""

echo_command "# Step 3: Monitor API in real-time"
echo "python log_monitor.py --follow --logger access"
echo ""

# ============================================================================
# EXAMPLE 8: Security Auditing
# ============================================================================

echo_section "Example 8: Security Auditing"

echo "Workflow: Auditing user actions"
echo ""

echo_command "# Step 1: Export all audit logs for the month"
echo "python log_analyzer.py query --logger audit --last 30d --output-format csv -o audit_$(date +%Y%m).csv"
echo ""

echo_command "# Step 2: Find all admin actions"
echo "python log_analyzer.py query --logger audit --keyword 'admin' --last 30d"
echo ""

echo_command "# Step 3: Find all delete operations"
echo "python log_analyzer.py query --logger audit --keyword 'delete' --last 30d"
echo ""

echo_command "# Step 4: Monitor privileged operations in real-time"
echo "python log_monitor.py --follow --logger audit --alert-on 'delete' 'emergency' 'disconnect'"
echo ""

# ============================================================================
# EXAMPLE 9: Scheduled Reports (Cron)
# ============================================================================

echo_section "Example 9: Scheduled Reports (Cron Jobs)"

echo "Add these to your crontab (crontab -e):"
echo ""

echo_command "# Daily report at 1 AM"
echo "0 1 * * * cd /path/to/LabLink/server && python generate_log_reports.py --period daily -o /var/reports/daily_\$(date +\%Y\%m\%d).txt"
echo ""

echo_command "# Weekly report on Monday at 2 AM"
echo "0 2 * * 1 cd /path/to/LabLink/server && python generate_log_reports.py --period weekly --format html -o /var/reports/weekly_\$(date +\%Y\%m\%d).html"
echo ""

echo_command "# Anomaly detection every 6 hours"
echo "0 */6 * * * cd /path/to/LabLink/server && python log_analyzer.py anomaly --sensitivity medium > /var/reports/anomalies.txt"
echo ""

# ============================================================================
# EXAMPLE 10: Advanced Queries with jq
# ============================================================================

echo_section "Example 10: Advanced JSON Queries with jq"

echo "If jq is installed, you can do powerful filtering:"
echo ""

echo_command "# Find errors from specific equipment"
echo "python log_analyzer.py query --level ERROR --output-format json | jq '.[] | select(.equipment_id == \"PSU_001\")'"
echo ""

echo_command "# Get unique error messages"
echo "python log_analyzer.py query --level ERROR --output-format json | jq -r '.[].message' | sort -u"
echo ""

echo_command "# Count errors by hour"
echo "python log_analyzer.py query --level ERROR --output-format json | jq -r '.[].timestamp[:13]' | sort | uniq -c"
echo ""

echo_command "# Find slowest operations"
echo "python log_analyzer.py query --output-format json | jq '.[] | select(.duration_ms != null) | {op: .message, duration: .duration_ms}' | jq -s 'sort_by(.duration) | reverse | .[0:10]'"
echo ""

# ============================================================================
# EXAMPLE 11: Quick Testing
# ============================================================================

echo_section "Example 11: Quick Test of Log Analysis Tools"

echo -e "${YELLOW}Running quick test to verify tools are working...${NC}\n"

# Create logs directory if it doesn't exist
mkdir -p ./logs

# Test log analyzer
if python log_analyzer.py --help > /dev/null 2>&1; then
    echo -e "${GREEN}✓ log_analyzer.py is working${NC}"
else
    echo -e "${YELLOW}✗ log_analyzer.py has issues${NC}"
fi

# Test log monitor
if python log_monitor.py --help > /dev/null 2>&1; then
    echo -e "${GREEN}✓ log_monitor.py is working${NC}"
else
    echo -e "${YELLOW}✗ log_monitor.py has issues${NC}"
fi

# Test report generator
if python generate_log_reports.py --help > /dev/null 2>&1; then
    echo -e "${GREEN}✓ generate_log_reports.py is working${NC}"
else
    echo -e "${YELLOW}✗ generate_log_reports.py has issues${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}All examples ready to use!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "To get started:"
echo "1. Make sure your server is running to generate logs"
echo "2. Try: python log_analyzer.py query --last 1h"
echo "3. Try: python log_monitor.py --follow"
echo "4. See LOG_ANALYSIS_GUIDE.md for full documentation"
