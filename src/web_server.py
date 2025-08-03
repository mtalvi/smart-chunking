"""
Lightweight Flask web server for serving log analysis results.

Provides an interactive web interface to browse and filter analysis results
without the complexity of Streamlit.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from flask import Flask, render_template_string, request, jsonify, send_from_directory
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from src.report_generator import ReportGenerator


class LogAnalysisWebServer:
    """Lightweight web server for log analysis results."""
    
    def __init__(self, results_path: str = "results.json", port: int = 5000, host: str = "127.0.0.1"):
        """Initialize the web server."""
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the web server. Install with: pip install flask")
        
        self.results_path = results_path
        self.port = port
        self.host = host
        self.app = Flask(__name__)
        self.report_generator = ReportGenerator(results_path)
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            """Main dashboard page."""
            return render_template_string(self._get_main_template())
        
        @self.app.route('/api/summary')
        def api_summary():
            """API endpoint for summary data."""
            try:
                data = self.report_generator.load_results()
                summary = data['summary']
                
                # Calculate additional metrics  
                error_rate = 0
                # Handle different JSON structures
                total_lines = summary.get('processing_stats', {}).get('total_lines_processed', summary.get('total_lines_processed', 0))
                total_errors = summary.get('total_errors', summary.get('total_errors_found', 0))
                
                if total_lines > 0:
                    error_rate = (total_errors / total_lines) * 100
                
                # Flatten processing_stats into summary for backward compatibility
                if 'processing_stats' in summary:
                    summary.update(summary['processing_stats'])
                if 'total_errors' in summary and 'total_errors_found' not in summary:
                    summary['total_errors_found'] = summary['total_errors']
                
                error_types = self.report_generator._calculate_error_types(data['results'])
                files_with_errors = self.report_generator._get_files_with_errors(data['results'])
                
                return jsonify({
                    'summary': summary,
                    'error_rate': error_rate,
                    'error_types': error_types,
                    'files_with_errors': files_with_errors,
                    'total_files_with_errors': len(files_with_errors)
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/results')
        def api_results():
            """API endpoint for results data with filtering."""
            try:
                data = self.report_generator.load_results()
                results = data['results']
                
                # Apply filters from query parameters
                error_type = request.args.get('error_type')
                min_confidence = request.args.get('min_confidence', type=float)
                file_path = request.args.get('file_path')
                detector = request.args.get('detector')
                
                filtered_results = results
                
                if error_type:
                    filtered_results = [r for r in filtered_results if r['error_type'] == error_type]
                
                if min_confidence is not None:
                    filtered_results = [r for r in filtered_results if r['confidence'] >= min_confidence]
                
                if file_path:
                    filtered_results = [r for r in filtered_results if file_path in r['file_path']]
                
                if detector:
                    filtered_results = [r for r in filtered_results if r['detector_name'] == detector]
                
                # Pagination
                page = request.args.get('page', 1, type=int)
                per_page = request.args.get('per_page', 10, type=int)
                start = (page - 1) * per_page
                end = start + per_page
                
                paginated_results = filtered_results[start:end]
                
                return jsonify({
                    'results': paginated_results,
                    'total': len(filtered_results),
                    'page': page,
                    'per_page': per_page,
                    'total_pages': (len(filtered_results) + per_page - 1) // per_page
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/result/<int:result_id>')
        def api_result_detail(result_id):
            """API endpoint for individual result details."""
            try:
                data = self.report_generator.load_results()
                results = data['results']
                
                if 0 <= result_id < len(results):
                    return jsonify({
                        'result': results[result_id],
                        'index': result_id
                    })
                else:
                    return jsonify({'error': 'Result not found'}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/export/<format>')
        def export_data(format):
            """Export data in various formats."""
            try:
                if format == 'html':
                    output_path = 'temp_report.html'
                    self.report_generator.generate_html_report(output_path)
                    return send_from_directory('.', output_path, as_attachment=True, 
                                             download_name=f'analysis_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html')
                
                elif format == 'json':
                    output_path = 'temp_summary.json'
                    self.report_generator.generate_json_summary(output_path)
                    return send_from_directory('.', output_path, as_attachment=True,
                                             download_name=f'analysis_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
                
                elif format == 'text':
                    output_path = 'temp_report.txt'
                    self.report_generator.generate_text_report(output_path)
                    return send_from_directory('.', output_path, as_attachment=True,
                                             download_name=f'analysis_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
                
                else:
                    return jsonify({'error': 'Unsupported format'}), 400
            except Exception as e:
                return jsonify({'error': str(e)}), 500
    
    def _get_main_template(self) -> str:
        """Get the main HTML template."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log Analysis Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }
        
        .header h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .metric-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        
        .metric-card:hover {
            transform: translateY(-2px);
        }
        
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
            margin-bottom: 5px;
        }
        
        .metric-label {
            color: #666;
            font-size: 0.9em;
        }
        
        .controls {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .controls h3 {
            margin-bottom: 15px;
            color: #2c3e50;
        }
        
        .filter-group {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .filter-item {
            display: flex;
            flex-direction: column;
        }
        
        .filter-item label {
            margin-bottom: 5px;
            font-weight: 500;
            color: #555;
        }
        
        .filter-item select,
        .filter-item input {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
        }
        
        .button-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            transition: background-color 0.2s;
        }
        
        .btn-primary {
            background: #3498db;
            color: white;
        }
        
        .btn-primary:hover {
            background: #2980b9;
        }
        
        .btn-secondary {
            background: #95a5a6;
            color: white;
        }
        
        .btn-secondary:hover {
            background: #7f8c8d;
        }
        
        .btn-success {
            background: #27ae60;
            color: white;
        }
        
        .btn-success:hover {
            background: #229954;
        }
        
        .results-container {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }
        
        .pagination {
            display: flex;
            gap: 5px;
            align-items: center;
            margin-top: 20px;
        }
        
        .pagination button {
            padding: 8px 12px;
            border: 1px solid #ddd;
            background: white;
            cursor: pointer;
            border-radius: 3px;
        }
        
        .pagination button:hover {
            background: #f8f9fa;
        }
        
        .pagination button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .pagination .current {
            background: #3498db;
            color: white;
            border-color: #3498db;
        }
        
        .result-item {
            border: 1px solid #eee;
            border-radius: 8px;
            margin-bottom: 15px;
            padding: 15px;
            transition: all 0.2s;
        }
        
        .result-item:hover {
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transform: translateY(-1px);
        }
        
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .error-type-badge {
            background: #e74c3c;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .confidence-badge {
            background: #27ae60;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .result-details {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        
        .original-line {
            background: #2c3e50;
            color: #ecf0f1;
            padding: 10px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            margin-bottom: 10px;
            overflow-x: auto;
            border-left: 4px solid #e74c3c;
        }
        
        .context-toggle {
            background: none;
            border: 1px solid #3498db;
            color: #3498db;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.8em;
        }
        
        .context-toggle:hover {
            background: #3498db;
            color: white;
        }
        
        .context {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 10px;
            margin-top: 10px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            max-height: 300px;
            overflow-y: auto;
            display: none;
        }
        
        .context.show {
            display: block;
        }
        
        .context-line {
            padding: 1px 0;
        }
        
        .context-line.error {
            background: #fff3cd;
            font-weight: bold;
            padding: 2px 5px;
            margin: 2px -5px;
            border-left: 3px solid #ffc107;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .filter-group {
                grid-template-columns: 1fr;
            }
            
            .button-group {
                justify-content: center;
            }
            
            .results-header {
                flex-direction: column;
                gap: 10px;
            }
            
            .result-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 5px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Log Analysis Dashboard</h1>
            <p>Interactive analysis results viewer</p>
        </div>
        
        <div class="metrics" id="metrics">
            <!-- Metrics will be loaded here -->
        </div>
        
        <div class="controls">
            <h3>Filters & Controls</h3>
            <div class="filter-group">
                <div class="filter-item">
                    <label for="errorType">Error Type:</label>
                    <select id="errorType">
                        <option value="">All Types</option>
                    </select>
                </div>
                <div class="filter-item">
                    <label for="minConfidence">Min Confidence:</label>
                    <input type="number" id="minConfidence" min="0" max="1" step="0.1" placeholder="0.0">
                </div>
                <div class="filter-item">
                    <label for="filePath">File Path:</label>
                    <input type="text" id="filePath" placeholder="Filter by file path...">
                </div>
                <div class="filter-item">
                    <label for="detector">Detector:</label>
                    <select id="detector">
                        <option value="">All Detectors</option>
                    </select>
                </div>
            </div>
            <div class="button-group">
                <button class="btn btn-primary" onclick="applyFilters()">Apply Filters</button>
                <button class="btn btn-secondary" onclick="clearFilters()">Clear Filters</button>
                <button class="btn btn-success" onclick="exportData('html')">Export HTML</button>
                <button class="btn btn-success" onclick="exportData('json')">Export JSON</button>
                <button class="btn btn-success" onclick="exportData('text')">Export Text</button>
            </div>
        </div>
        
        <div class="results-container">
            <div class="results-header">
                <h3>Detection Results</h3>
                <div id="results-info"></div>
            </div>
            <div id="results">
                <div class="loading">Loading results...</div>
            </div>
            <div class="pagination" id="pagination"></div>
        </div>
    </div>

    <script>
        let currentData = {};
        let currentPage = 1;
        let currentFilters = {};
        
        // Load initial data
        async function loadData() {
            try {
                const summaryResponse = await fetch('/api/summary');
                const summaryData = await summaryResponse.json();
                
                if (summaryData.error) {
                    throw new Error(summaryData.error);
                }
                
                displayMetrics(summaryData);
                populateFilterOptions(summaryData);
                loadResults();
            } catch (error) {
                document.getElementById('metrics').innerHTML = 
                    `<div class="error-message">Error loading data: ${error.message}</div>`;
            }
        }
        
        function displayMetrics(data) {
            const metrics = document.getElementById('metrics');
            const summary = data.summary;
            
            metrics.innerHTML = `
                <div class="metric-card">
                    <div class="metric-value">${summary.total_files_processed}</div>
                    <div class="metric-label">Files Processed</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${(summary.total_lines_processed || 0).toLocaleString()}</div>
                    <div class="metric-label">Lines Processed</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${summary.total_errors_found}</div>
                    <div class="metric-label">Errors Found</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${summary.processing_time.toFixed(2)}s</div>
                    <div class="metric-label">Processing Time</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${data.error_rate.toFixed(4)}%</div>
                    <div class="metric-label">Error Rate</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${data.total_files_with_errors}</div>
                    <div class="metric-label">Files with Errors</div>
                </div>
            `;
        }
        
        function populateFilterOptions(data) {
            const errorTypeSelect = document.getElementById('errorType');
            const detectorSelect = document.getElementById('detector');
            
            // Populate error types
            Object.keys(data.error_types).forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = `${type} (${data.error_types[type]})`;
                errorTypeSelect.appendChild(option);
            });
            
            // We'll populate detectors when we load results
        }
        
        async function loadResults(page = 1) {
            currentPage = page;
            
            // Build query parameters
            const params = new URLSearchParams({
                page: page,
                per_page: 10,
                ...currentFilters
            });
            
            try {
                const response = await fetch(`/api/results?${params}`);
                const data = await response.json();
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                currentData = data;
                displayResults(data);
                displayPagination(data);
                updateResultsInfo(data);
                
                // Update detector options if not already done
                updateDetectorOptions(data.results);
            } catch (error) {
                document.getElementById('results').innerHTML = 
                    `<div class="error-message">Error loading results: ${error.message}</div>`;
            }
        }
        
        function displayResults(data) {
            const resultsContainer = document.getElementById('results');
            
            if (data.results.length === 0) {
                resultsContainer.innerHTML = '<p>No results match the current filters.</p>';
                return;
            }
            
            const resultsHtml = data.results.map((result, index) => {
                const globalIndex = (data.page - 1) * data.per_page + index;
                
                // Build context HTML
                let contextHtml = '';
                if (result.context_before || result.context_after) {
                    contextHtml = '<div class="context" id="context-' + globalIndex + '">';
                    
                    // Context before
                    (result.context_before || []).forEach(line => {
                        if (line.trim()) {
                            contextHtml += `<div class="context-line">${escapeHtml(line)}</div>`;
                        }
                    });
                    
                    // Original line (highlighted)
                    contextHtml += `<div class="context-line error">${escapeHtml(result.original_line)}</div>`;
                    
                    // Context after
                    (result.context_after || []).forEach(line => {
                        if (line.trim()) {
                            contextHtml += `<div class="context-line">${escapeHtml(line)}</div>`;
                        }
                    });
                    
                    contextHtml += '</div>';
                }
                
                // Build match details
                let matchDetails = '';
                if (result.matched_patterns && result.matched_patterns.length > 0) {
                    matchDetails += `<strong>Patterns:</strong> ${result.matched_patterns.join(', ')}<br>`;
                }
                if (result.matched_semantic_phrases && result.matched_semantic_phrases.length > 0) {
                    const phrases = result.matched_semantic_phrases.map(([phrase, score]) => 
                        `${phrase} (${score.toFixed(3)})`).join(', ');
                    matchDetails += `<strong>Semantic:</strong> ${phrases}<br>`;
                }
                
                // Build grouping info
                let groupingInfo = '';
                if (result.match_details && result.match_details.grouping_info) {
                    const grouping = result.match_details.grouping_info;
                    if (grouping.type === 'retry_sequence') {
                        groupingInfo = `<strong>Retry Sequence:</strong> ${grouping.total_attempts} attempts for '${grouping.task_signature}'<br>`;
                    } else if (grouping.type === 'workflow_sequence') {
                        const workflowInfo = result.match_details.workflow_grouping_info || {};
                        const components = workflowInfo.workflow_components || [];
                        groupingInfo = `<strong>Workflow:</strong> ${components.length} components, ${workflowInfo.total_retry_attempts || 0} total retries<br>`;
                    }
                }
                
                return `
                    <div class="result-item">
                        <div class="result-header">
                            <div>
                                <span class="error-type-badge">${result.error_type.toUpperCase()}</span>
                                <span class="confidence-badge">${result.confidence.toFixed(2)}</span>
                            </div>
                            <div>#${globalIndex + 1}</div>
                        </div>
                        <div class="result-details">
                            <strong>File:</strong> ${result.file_path}<br>
                            <strong>Line:</strong> ${result.line_number}<br>
                            <strong>Detector:</strong> ${result.detector_name}<br>
                            ${groupingInfo}
                            ${matchDetails}
                        </div>
                        <div class="original-line">${escapeHtml(result.original_line)}</div>
                        ${contextHtml ? `<button class="context-toggle" onclick="toggleContext(${globalIndex})">Show Context</button>` : ''}
                        ${contextHtml}
                    </div>
                `;
            }).join('');
            
            resultsContainer.innerHTML = resultsHtml;
        }
        
        function displayPagination(data) {
            const pagination = document.getElementById('pagination');
            
            if (data.total_pages <= 1) {
                pagination.innerHTML = '';
                return;
            }
            
            let paginationHtml = '';
            
            // Previous button
            paginationHtml += `<button onclick="loadResults(${data.page - 1})" ${data.page === 1 ? 'disabled' : ''}>Previous</button>`;
            
            // Page numbers
            for (let i = Math.max(1, data.page - 2); i <= Math.min(data.total_pages, data.page + 2); i++) {
                paginationHtml += `<button onclick="loadResults(${i})" ${i === data.page ? 'class="current"' : ''}>${i}</button>`;
            }
            
            // Next button
            paginationHtml += `<button onclick="loadResults(${data.page + 1})" ${data.page === data.total_pages ? 'disabled' : ''}>Next</button>`;
            
            pagination.innerHTML = paginationHtml;
        }
        
        function updateResultsInfo(data) {
            document.getElementById('results-info').textContent = 
                `Showing ${data.results.length} of ${data.total} results (Page ${data.page} of ${data.total_pages})`;
        }
        
        function updateDetectorOptions(results) {
            const detectorSelect = document.getElementById('detector');
            
            // Get unique detectors
            const detectors = [...new Set(results.map(r => r.detector_name))];
            
            // Clear existing options (except "All Detectors")
            while (detectorSelect.children.length > 1) {
                detectorSelect.removeChild(detectorSelect.lastChild);
            }
            
            detectors.forEach(detector => {
                const option = document.createElement('option');
                option.value = detector;
                option.textContent = detector;
                detectorSelect.appendChild(option);
            });
        }
        
        function applyFilters() {
            currentFilters = {};
            
            const errorType = document.getElementById('errorType').value;
            if (errorType) currentFilters.error_type = errorType;
            
            const minConfidence = document.getElementById('minConfidence').value;
            if (minConfidence) currentFilters.min_confidence = parseFloat(minConfidence);
            
            const filePath = document.getElementById('filePath').value;
            if (filePath) currentFilters.file_path = filePath;
            
            const detector = document.getElementById('detector').value;
            if (detector) currentFilters.detector = detector;
            
            loadResults(1);
        }
        
        function clearFilters() {
            currentFilters = {};
            document.getElementById('errorType').value = '';
            document.getElementById('minConfidence').value = '';
            document.getElementById('filePath').value = '';
            document.getElementById('detector').value = '';
            loadResults(1);
        }
        
        function toggleContext(index) {
            const context = document.getElementById('context-' + index);
            const button = context.previousElementSibling;
            
            if (context.classList.contains('show')) {
                context.classList.remove('show');
                button.textContent = 'Show Context';
            } else {
                context.classList.add('show');
                button.textContent = 'Hide Context';
            }
        }
        
        async function exportData(format) {
            try {
                const response = await fetch(`/export/${format}`);
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = response.headers.get('Content-Disposition').split('filename=')[1];
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                } else {
                    throw new Error('Export failed');
                }
            } catch (error) {
                alert(`Export failed: ${error.message}`);
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Initialize the dashboard
        loadData();
    </script>
</body>
</html>"""
    
    def run(self, debug: bool = False):
        """Run the Flask web server."""
        print(f"Starting Log Analysis Web Server...")
        print(f"Dashboard will be available at: http://{self.host}:{self.port}")
        print(f"Results file: {self.results_path}")
        print(f"Press Ctrl+C to stop the server")
        
        self.app.run(host=self.host, port=self.port, debug=debug)


def start_web_server(results_path: str = "results.json", port: int = 5000, host: str = "127.0.0.1", debug: bool = False):
    """Start the web server with the given configuration."""
    server = LogAnalysisWebServer(results_path, port, host)
    server.run(debug)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Start log analysis web server")
    parser.add_argument("--results", default="results.json", help="Results JSON file path")
    parser.add_argument("--port", type=int, default=5000, help="Port to run server on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    
    args = parser.parse_args()
    
    start_web_server(args.results, args.port, args.host, args.debug) 