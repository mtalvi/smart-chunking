"""
Advanced report generator for log analysis results.

Provides multiple ways to serve analysis results to users:
1. Static HTML reports with modern, responsive design
2. Enhanced CLI output with rich formatting
3. JSON summaries for programmatic access
4. Detailed text reports for sharing
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import asdict

from .models.results import AnalysisResults, DetectionResult


class ReportGenerator:
    """Advanced report generator for log analysis results."""
    
    def __init__(self, results_path: Optional[str] = None):
        """Initialize the report generator."""
        self.results_path = results_path or "results.json"
        self.results_data = None
        
    def load_results(self) -> Dict[str, Any]:
        """Load results from JSON file."""
        if self.results_data is None:
            try:
                with open(self.results_path, 'r', encoding='utf-8') as f:
                    self.results_data = json.load(f)
            except FileNotFoundError:
                raise FileNotFoundError(f"Results file not found: {self.results_path}")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in results file: {e}")
        
        return self.results_data
    
    def generate_html_report(self, output_path: str = "analysis_report.html") -> str:
        """Generate a modern, responsive HTML report."""
        data = self.load_results()
        
        html_content = self._create_html_template()
        
        # Generate summary section
        summary_html = self._generate_summary_html(data['summary'])
        
        # Generate clustering section
        clustering_html = self._generate_clustering_html(data['results'])
        
        # Generate results section
        results_html = self._generate_results_html(data['results'])
        
        # Generate statistics section
        stats_html = self._generate_statistics_html(data)
        
        # Replace placeholders in template
        html_content = html_content.replace('{{SUMMARY_CONTENT}}', summary_html)
        html_content = html_content.replace('{{CLUSTERING_CONTENT}}', clustering_html)
        html_content = html_content.replace('{{RESULTS_CONTENT}}', results_html)
        html_content = html_content.replace('{{STATISTICS_CONTENT}}', stats_html)
        html_content = html_content.replace('{{GENERATION_TIME}}', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def generate_cli_report(self, show_context: bool = True, show_details: bool = True) -> str:
        """Generate an enhanced CLI report with rich formatting."""
        data = self.load_results()
        report = []
        
        # Header
        report.append("=" * 80)
        report.append("🔍 LOG ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")
        
                # Summary
        summary = data['summary']
        report.append("📊 SUMMARY")
        report.append("-" * 40)
        report.append(f"• Total Files Processed: {summary['total_files_processed']}")
        report.append(f"• Total Lines Processed: {summary['total_lines_processed']:,}")
        report.append(f"• Total Errors Found: {summary['total_errors_found']}")
        report.append(f"• Processing Time: {summary['processing_time']:.2f} seconds")

        if summary['total_errors_found'] > 0:
            error_rate = (summary['total_errors_found'] / summary['total_lines_processed']) * 100
            report.append(f"• Error Rate: {error_rate:.4f}%")

        report.append("")

        # Clustering Summary
        clustering_info = self._analyze_clustering(data['results'])
        if clustering_info['clusters_found']:
            report.append("🔗 CLUSTERING ANALYSIS")
            report.append("-" * 40)
            report.append(f"• Total Clusters: {clustering_info['total_clusters']}")
            report.append(f"• Clustered Errors: {clustering_info['clustered_errors']} ({clustering_info['clustering_percentage']:.1f}%)")
            report.append(f"• Unique Errors: {clustering_info['noise_points']} unclustered")
            if clustering_info['largest_cluster_size'] > 1:
                report.append(f"• Largest Cluster: {clustering_info['largest_cluster_size']} similar errors")
            report.append("")
        
        # Error types breakdown
        error_types = self._calculate_error_types(data['results'])
        if error_types:
            report.append("📋 ERROR TYPES")
            report.append("-" * 40)
            for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / summary['total_errors_found']) * 100
                report.append(f"• {error_type}: {count} ({percentage:.1f}%)")
            report.append("")
        
        # Files with errors
        files_with_errors = self._get_files_with_errors(data['results'])
        if files_with_errors:
            report.append("📁 FILES WITH ERRORS")
            report.append("-" * 40)
            for file_path, count in sorted(files_with_errors.items(), key=lambda x: x[1], reverse=True):
                report.append(f"• {file_path}: {count} errors")
            report.append("")
        
        # Show clustering results first if available
        clustering_info = self._analyze_clustering(data['results'])
        if clustering_info['clusters_found']:
            report.append("🔗 ERROR CLUSTERS")
            report.append("-" * 40)
            
            # Group results by cluster
            results_by_cluster = {}
            for result in data['results']:
                cluster_id = result.get('match_details', {}).get('cluster_id', -1)
                if cluster_id not in results_by_cluster:
                    results_by_cluster[cluster_id] = []
                results_by_cluster[cluster_id].append(result)
            
            # Show actual clusters first
            cluster_num = 1
            for cluster_id in sorted(results_by_cluster.keys()):
                if cluster_id == -1:  # Skip noise for now
                    continue
                
                cluster_results = results_by_cluster[cluster_id]
                representative = next((r for r in cluster_results if r.get('match_details', {}).get('is_representative')), cluster_results[0])
                
                report.append(f"\n🔗 CLUSTER {cluster_num} ({len(cluster_results)} similar errors)")
                report.append(f"    Type: {cluster_results[0]['error_type'].upper()}")
                report.append(f"    Description: {representative.get('match_details', {}).get('cluster_description', 'Similar errors')}")
                
                files = list(set(r['file_path'] for r in cluster_results))
                if len(files) <= 3:
                    report.append(f"    Files: {', '.join(files)}")
                else:
                    report.append(f"    Files: {files[0]}, {files[1]}, {files[2]} (+{len(files)-3} more)")
                
                report.append(f"    Representative Error:")
                report.append(f"      File: {representative['file_path']}:{representative['line_number']}")
                report.append(f"      Line: {representative['original_line'][:100]}{'...' if len(representative['original_line']) > 100 else ''}")
                
                cluster_num += 1
            
            # Show noise points
            if -1 in results_by_cluster:
                noise_results = results_by_cluster[-1]
                report.append(f"\n🔀 UNCLUSTERED ERRORS ({len(noise_results)} unique issues)")
                for result in noise_results[:3]:  # Show first 3
                    report.append(f"    • {result['error_type']}: {result['file_path']}:{result['line_number']}")
                if len(noise_results) > 3:
                    report.append(f"    • ... and {len(noise_results) - 3} more unique errors")
            
            report.append("")

        # Individual results
        if data['results']:
            report.append("🚨 DETAILED RESULTS")
            report.append("-" * 40)
            
            for i, result in enumerate(data['results'], 1):
                cluster_info = ""
                if 'match_details' in result and result['match_details']:
                    details = result['match_details']
                    cluster_id = details.get('cluster_id', -1)
                    if cluster_id != -1:
                        cluster_size = details.get('cluster_size', 1)
                        is_rep = "★" if details.get('is_representative') else ""
                        cluster_info = f" [Cluster {cluster_id}: {cluster_size} errors{is_rep}]"
                    else:
                        cluster_info = " [Unique error]"
                
                report.append(f"\n[{i}] {result['error_type'].upper()}{cluster_info}")
                report.append(f"    File: {result['file_path']}")
                report.append(f"    Line: {result['line_number']}")
                report.append(f"    Confidence: {result['confidence']:.2f}")
                report.append(f"    Detector: {result['detector_name']}")
                
                # Show grouped information if available
                if 'match_details' in result and result['match_details']:
                    details = result['match_details']
                    if 'grouping_info' in details:
                        grouping = details['grouping_info']
                        if grouping['type'] == 'retry_sequence':
                            report.append(f"    Retry Attempts: {grouping['total_attempts']}")
                            report.append(f"    Task: {grouping['task_signature']}")
                        elif grouping['type'] == 'workflow_sequence':
                            report.append(f"    Workflow Components: {len(details.get('workflow_grouping_info', {}).get('workflow_components', []))}")
                
                # Original line
                report.append(f"    Original Line:")
                report.append(f"      {result['original_line']}")
                
                # Context
                if show_context and (result.get('context_before') or result.get('context_after')):
                    report.append("    Context:")
                    for line in result.get('context_before', [])[-3:]:  # Last 3 before
                        if line.strip():
                            report.append(f"      {line}")
                    report.append(f"    → {result['original_line']}")
                    for line in result.get('context_after', [])[:3]:  # First 3 after
                        if line.strip():
                            report.append(f"      {line}")
                
                # Match details
                if show_details:
                    if result.get('matched_patterns'):
                        report.append(f"    Matched Patterns: {', '.join(result['matched_patterns'])}")
                    if result.get('matched_semantic_phrases'):
                        phrases = [f"{phrase} ({score:.3f})" for phrase, score in result['matched_semantic_phrases']]
                        report.append(f"    Semantic Matches: {', '.join(phrases)}")
        
        report.append("\n" + "=" * 80)
        report.append(f"Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(report)
    
    def generate_json_summary(self, output_path: str = "analysis_summary.json") -> str:
        """Generate a structured JSON summary for programmatic access."""
        data = self.load_results()
        
        summary = {
            "analysis_metadata": {
                "generated_at": datetime.now().isoformat(),
                "results_file": self.results_path,
                "total_results": len(data['results'])
            },
            "processing_summary": data['summary'],
            "error_analysis": {
                "error_types": self._calculate_error_types(data['results']),
                "files_affected": self._get_files_with_errors(data['results']),
                "confidence_distribution": self._calculate_confidence_distribution(data['results']),
                "detector_performance": self._calculate_detector_stats(data['results'])
            },
            "workflow_analysis": self._analyze_workflows(data['results']),
            "retry_analysis": self._analyze_retries(data['results']),
            "top_errors": self._get_top_errors(data['results'], limit=10)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        return output_path
    
    def generate_text_report(self, output_path: str = "analysis_report.txt") -> str:
        """Generate a detailed text report suitable for sharing."""
        cli_report = self.generate_cli_report(show_context=True, show_details=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cli_report)
        
        return output_path
    
    def print_quick_summary(self) -> None:
        """Print a quick summary to console."""
        data = self.load_results()
        summary = data['summary']
        
        print("\n🔍 LOG ANALYSIS QUICK SUMMARY")
        print("=" * 40)
        print(f"Files Processed: {summary['total_files_processed']}")
        print(f"Lines Processed: {summary['total_lines_processed']:,}")
        print(f"Errors Found: {summary['total_errors_found']}")
        print(f"Processing Time: {summary['processing_time']:.2f}s")
        
        if summary['total_errors_found'] > 0:
            error_rate = (summary['total_errors_found'] / summary['total_lines_processed']) * 100
            print(f"Error Rate: {error_rate:.4f}%")
        
        # Top error types
        error_types = self._calculate_error_types(data['results'])
        if error_types:
            print("\nTop Error Types:")
            for error_type, count in list(sorted(error_types.items(), key=lambda x: x[1], reverse=True))[:5]:
                print(f"  • {error_type}: {count}")
        
        print("=" * 40)
    
    def _create_html_template(self) -> str:
        """Create the HTML template for the report."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log Analysis Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #2c3e50;
            background: #f8f9fa;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: #ffffff;
            border-radius: 8px;
            padding: 40px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            border: 1px solid #e9ecef;
            text-align: center;
        }
        
        .header h1 {
            color: #1a202c;
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 600;
        }
        
        .header .subtitle {
            color: #7f8c8d;
            font-size: 1.1em;
        }
        
        .card {
            background: #ffffff;
            border-radius: 8px;
            padding: 30px;
            margin-bottom: 25px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            border: 1px solid #e9ecef;
        }
        
        .card h2 {
            color: #1a202c;
            margin-bottom: 20px;
            font-size: 1.5em;
            border-bottom: 1px solid #e9ecef;
            padding-bottom: 12px;
            font-weight: 600;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .metric {
            background: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 6px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            border: 1px solid #34495e;
        }
        
        .metric .value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .metric .label {
            font-size: 0.9em;
            opacity: 0.9;
        }
        
        .error-item {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            transition: all 0.3s ease;
        }
        
        .error-item:hover {
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
        }
        
        .error-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .error-type {
            background: #e74c3c;
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: bold;
        }
        
        .confidence {
            background: #27ae60;
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: bold;
        }
        
        .error-details {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 15px;
        }
        
        .original-line {
            background: #2c3e50;
            color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            line-height: 1.4;
            overflow-x: auto;
            border-left: 4px solid #e74c3c;
        }
        
        .cluster-section {
            background: #f8f9fa;
            border: 2px solid #007bff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        .cluster-item {
            background: #ffffff;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #007bff;
        }
        
        .cluster-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .cluster-title {
            color: #007bff;
            font-weight: bold;
            font-size: 1.1em;
        }
        
        .cluster-badge {
            background: #007bff;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .cluster-description {
            color: #6c757d;
            font-style: italic;
            margin-bottom: 10px;
        }
        
        .cluster-files {
            color: #495057;
            font-size: 0.9em;
            margin-bottom: 8px;
        }
        
        .cluster-representative {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 10px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
        }
        
        .noise-section {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
        }
        
        .noise-title {
            color: #856404;
            font-weight: bold;
            margin-bottom: 10px;
        }
        
        .cluster-tag {
            display: inline-block;
            background: #e9ecef;
            color: #495057;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 0.75em;
            margin-left: 8px;
        }
        
        .cluster-tag.representative {
            background: #007bff;
            color: white;
        }
        
        .cluster-tag.unique {
            background: #6c757d;
            color: white;
        }
        
        .context {
            background: #f4f4f4;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            margin-top: 10px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .context-line {
            padding: 2px 0;
            border-left: 3px solid transparent;
        }
        
        .context-line.error {
            background: #ffebee;
            border-left-color: #e74c3c;
            font-weight: bold;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        .footer {
            text-align: center;
            color: #6c757d;
            margin-top: 30px;
            font-size: 0.9em;
            padding: 20px;
            background: #ffffff;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header h1 {
                font-size: 2em;
            }
            
            .summary-grid {
                grid-template-columns: 1fr;
            }
            
            .error-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Log Analysis Report</h1>
            <p class="subtitle">Comprehensive error detection and analysis results</p>
        </div>
        
        <div class="card">
            <h2>📊 Summary</h2>
            {{SUMMARY_CONTENT}}
        </div>
        
        {{CLUSTERING_CONTENT}}
        
        <div class="card">
            <h2>🚨 Detection Results</h2>
            {{RESULTS_CONTENT}}
        </div>
        
        <div class="card">
            <h2>📈 Statistics</h2>
            {{STATISTICS_CONTENT}}
        </div>
        
        <div class="footer">
            Generated on {{GENERATION_TIME}} by Log Error Extractor
        </div>
    </div>
</body>
</html>"""
    
    def _generate_summary_html(self, summary: Dict[str, Any]) -> str:
        """Generate the summary section HTML."""
        error_rate = 0
        if summary['total_lines_processed'] > 0:
            error_rate = (summary['total_errors_found'] / summary['total_lines_processed']) * 100
        
        return f"""
        <div class="summary-grid">
            <div class="metric">
                <div class="value">{summary['total_files_processed']}</div>
                <div class="label">Files Processed</div>
            </div>
            <div class="metric">
                <div class="value">{summary['total_lines_processed']:,}</div>
                <div class="label">Lines Processed</div>
            </div>
            <div class="metric">
                <div class="value">{summary['total_errors_found']}</div>
                <div class="label">Errors Found</div>
            </div>
            <div class="metric">
                <div class="value">{summary['processing_time']:.2f}s</div>
                <div class="label">Processing Time</div>
            </div>
            <div class="metric">
                <div class="value">{error_rate:.4f}%</div>
                <div class="label">Error Rate</div>
            </div>
        </div>
        """
    
    def _generate_clustering_html(self, results: List[Dict[str, Any]]) -> str:
        """Generate the clustering section HTML."""
        clustering_info = self._analyze_clustering(results)
        
        if not clustering_info['clusters_found']:
            return ""
        
        html_parts = []
        html_parts.append('<div class="card">')
        html_parts.append('<h2>🔗 Error Clustering Analysis</h2>')
        
        # Clustering summary
        html_parts.append('<div class="summary-grid">')
        html_parts.append(f'''
            <div class="metric">
                <div class="value">{clustering_info['total_clusters']}</div>
                <div class="label">Clusters Found</div>
            </div>
            <div class="metric">
                <div class="value">{clustering_info['clustered_errors']}</div>
                <div class="label">Clustered Errors</div>
            </div>
            <div class="metric">
                <div class="value">{clustering_info['noise_points']}</div>
                <div class="label">Unique Errors</div>
            </div>
            <div class="metric">
                <div class="value">{clustering_info['clustering_percentage']:.1f}%</div>
                <div class="label">Clustering Rate</div>
            </div>
        ''')
        html_parts.append('</div>')
        
        # Group results by cluster
        results_by_cluster = {}
        for result in results:
            cluster_id = result.get('match_details', {}).get('cluster_id', -1)
            if cluster_id not in results_by_cluster:
                results_by_cluster[cluster_id] = []
            results_by_cluster[cluster_id].append(result)
        
        # Show actual clusters
        cluster_num = 1
        for cluster_id in sorted(results_by_cluster.keys()):
            if cluster_id == -1:  # Skip noise for now
                continue
            
            cluster_results = results_by_cluster[cluster_id]
            representative = next((r for r in cluster_results if r.get('match_details', {}).get('is_representative')), cluster_results[0])
            
            html_parts.append('<div class="cluster-item">')
            html_parts.append('<div class="cluster-header">')
            html_parts.append(f'<div class="cluster-title">🔗 Cluster {cluster_num}</div>')
            html_parts.append(f'<div class="cluster-badge">{len(cluster_results)} errors</div>')
            html_parts.append('</div>')
            
            description = representative.get('match_details', {}).get('cluster_description', 'Similar errors')
            html_parts.append(f'<div class="cluster-description">{self._escape_html(description)}</div>')
            
            files = list(set(r['file_path'] for r in cluster_results))
            if len(files) <= 5:
                files_text = ', '.join(files)
            else:
                files_text = f"{', '.join(files[:3])} (+{len(files)-3} more files)"
            html_parts.append(f'<div class="cluster-files"><strong>Files:</strong> {self._escape_html(files_text)}</div>')
            
            html_parts.append('<div><strong>Representative Error:</strong></div>')
            html_parts.append('<div class="cluster-representative">')
            html_parts.append(f'{self._escape_html(representative["file_path"])}:{representative["line_number"]}<br>')
            rep_line = representative['original_line']
            if len(rep_line) > 120:
                rep_line = rep_line[:120] + '...'
            html_parts.append(self._escape_html(rep_line))
            html_parts.append('</div>')
            html_parts.append('</div>')
            
            cluster_num += 1
        
        # Show noise points
        if -1 in results_by_cluster:
            noise_results = results_by_cluster[-1]
            html_parts.append('<div class="noise-section">')
            html_parts.append(f'<div class="noise-title">🔀 Unclustered Errors ({len(noise_results)} unique issues)</div>')
            html_parts.append('<ul>')
            for result in noise_results[:5]:  # Show first 5
                html_parts.append(f'<li><strong>{result["error_type"]}:</strong> {self._escape_html(result["file_path"])}:{result["line_number"]}</li>')
            if len(noise_results) > 5:
                html_parts.append(f'<li><em>... and {len(noise_results) - 5} more unique errors</em></li>')
            html_parts.append('</ul>')
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        return "".join(html_parts)
    
    def _generate_results_html(self, results: List[Dict[str, Any]]) -> str:
        """Generate the results section HTML."""
        if not results:
            return "<p>No errors detected in the analyzed logs.</p>"
        
        html_parts = []
        
        for i, result in enumerate(results, 1):
            # Build context display
            context_html = ""
            if result.get('context_before') or result.get('context_after'):
                context_html = '<div class="context">'
                
                # Context before
                for line in result.get('context_before', []):
                    if line.strip():
                        context_html += f'<div class="context-line">{self._escape_html(line)}</div>'
                
                # Original line (highlighted)
                context_html += f'<div class="context-line error">{self._escape_html(result["original_line"])}</div>'
                
                # Context after
                for line in result.get('context_after', []):
                    if line.strip():
                        context_html += f'<div class="context-line">{self._escape_html(line)}</div>'
                
                context_html += '</div>'
            
            # Match details
            match_info = ""
            if result.get('matched_patterns'):
                match_info += f"<strong>Patterns:</strong> {', '.join(result['matched_patterns'])}<br>"
            if result.get('matched_semantic_phrases'):
                phrases = [f"{phrase} ({score:.3f})" for phrase, score in result['matched_semantic_phrases']]
                match_info += f"<strong>Semantic:</strong> {', '.join(phrases)}<br>"
            
            # Grouping info
            grouping_info = ""
            if 'match_details' in result and result['match_details']:
                details = result['match_details']
                if 'grouping_info' in details:
                    grouping = details['grouping_info']
                    if grouping['type'] == 'retry_sequence':
                        grouping_info = f"<strong>Retry Sequence:</strong> {grouping['total_attempts']} attempts for '{grouping['task_signature']}'<br>"
                    elif grouping['type'] == 'workflow_sequence':
                        workflow_info = details.get('workflow_grouping_info', {})
                        components = workflow_info.get('workflow_components', [])
                        grouping_info = f"<strong>Workflow:</strong> {len(components)} components, {workflow_info.get('total_retry_attempts', 0)} total retries<br>"
            
            # Add clustering information
            cluster_tag = ""
            if 'match_details' in result and result['match_details']:
                details = result['match_details']
                cluster_id = details.get('cluster_id', -1)
                if cluster_id != -1:
                    cluster_size = details.get('cluster_size', 1)
                    is_representative = details.get('is_representative', False)
                    tag_class = "representative" if is_representative else ""
                    star = "★ " if is_representative else ""
                    cluster_tag = f'<span class="cluster-tag {tag_class}">🔗 Cluster {cluster_id} ({cluster_size} errors) {star}</span>'
                else:
                    cluster_tag = '<span class="cluster-tag unique">🔀 Unique Error</span>'

            result_html = f"""
            <div class="error-item">
                <div class="error-header">
                    <div>
                        <span class="error-type">{result['error_type'].upper()}</span>
                        <span class="confidence">{result['confidence']:.2f}</span>
                        {cluster_tag}
                    </div>
                    <div>#{i}</div>
                </div>
                <div class="error-details">
                    <strong>File:</strong> {result['file_path']}<br>
                    <strong>Line:</strong> {result['line_number']}<br>
                    <strong>Detector:</strong> {result['detector_name']}<br>
                    {grouping_info}
                    {match_info}
                </div>
                <div class="original-line">{self._escape_html(result['original_line'])}</div>
                {context_html}
            </div>
            """
            
            html_parts.append(result_html)
        
        return "".join(html_parts)
    
    def _generate_statistics_html(self, data: Dict[str, Any]) -> str:
        """Generate the statistics section HTML."""
        results = data['results']
        
        # Error types
        error_types = self._calculate_error_types(results)
        error_types_html = ""
        if error_types:
            error_types_html = "<h3>Error Types Distribution</h3><ul>"
            for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(results)) * 100 if results else 0
                error_types_html += f"<li><strong>{error_type}:</strong> {count} ({percentage:.1f}%)</li>"
            error_types_html += "</ul>"
        
        # Files with errors
        files_with_errors = self._get_files_with_errors(results)
        files_html = ""
        if files_with_errors:
            files_html = "<h3>Files with Errors</h3><ul>"
            for file_path, count in sorted(files_with_errors.items(), key=lambda x: x[1], reverse=True):
                files_html += f"<li><strong>{file_path}:</strong> {count} errors</li>"
            files_html += "</ul>"
        
        return f"""
        <div class="stats-grid">
            <div class="chart-container">
                {error_types_html}
            </div>
            <div class="chart-container">
                {files_html}
            </div>
        </div>
        """
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#x27;'))
    
    def _calculate_error_types(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate error type distribution."""
        error_types = {}
        for result in results:
            error_type = result['error_type']
            error_types[error_type] = error_types.get(error_type, 0) + 1
        return error_types
    
    def _get_files_with_errors(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get files with error counts."""
        files = {}
        for result in results:
            file_path = result['file_path']
            files[file_path] = files.get(file_path, 0) + 1
        return files
    
    def _calculate_confidence_distribution(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate confidence score distribution."""
        distribution = {"high": 0, "medium": 0, "low": 0}
        for result in results:
            confidence = result['confidence']
            if confidence >= 0.8:
                distribution["high"] += 1
            elif confidence >= 0.6:
                distribution["medium"] += 1
            else:
                distribution["low"] += 1
        return distribution
    
    def _calculate_detector_stats(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate detector performance statistics."""
        stats = {}
        for result in results:
            detector = result['detector_name']
            stats[detector] = stats.get(detector, 0) + 1
        return stats
    
    def _analyze_workflows(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze workflow-related errors."""
        workflow_count = 0
        workflow_components = []
        
        for result in results:
            if 'match_details' in result and result['match_details']:
                details = result['match_details']
                if 'workflow_grouping_info' in details:
                    workflow_count += 1
                    components = details['workflow_grouping_info'].get('workflow_components', [])
                    workflow_components.extend(components)
        
        return {
            "total_workflow_errors": workflow_count,
            "unique_components": len(set(workflow_components)),
            "common_components": list(set(workflow_components))
        }
    
    def _analyze_retries(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze retry patterns."""
        retry_sequences = 0
        total_retries = 0
        
        for result in results:
            if 'match_details' in result and result['match_details']:
                details = result['match_details']
                if 'grouping_info' in details and details['grouping_info']['type'] == 'retry_sequence':
                    retry_sequences += 1
                    total_retries += details['grouping_info']['total_attempts']
        
        return {
            "retry_sequences": retry_sequences,
            "total_retry_attempts": total_retries,
            "avg_retries_per_sequence": total_retries / retry_sequences if retry_sequences > 0 else 0
        }
    
    def _get_top_errors(self, results: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """Get top errors by confidence."""
        sorted_results = sorted(results, key=lambda x: x['confidence'], reverse=True)
        return sorted_results[:limit]
    
    def _analyze_clustering(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze clustering information from results."""
        if not results:
            return {'clusters_found': False}
        
        # Check if any results have clustering information
        has_clustering = any(
            result.get('match_details', {}).get('cluster_id') is not None 
            for result in results
        )
        
        if not has_clustering:
            return {'clusters_found': False}
        
        # Count clusters and analyze
        cluster_counts = {}
        noise_count = 0
        
        for result in results:
            cluster_id = result.get('match_details', {}).get('cluster_id', -1)
            if cluster_id == -1:
                noise_count += 1
            else:
                cluster_counts[cluster_id] = cluster_counts.get(cluster_id, 0) + 1
        
        total_clusters = len(cluster_counts)
        clustered_errors = sum(cluster_counts.values())
        clustering_percentage = (clustered_errors / len(results)) * 100 if results else 0
        largest_cluster_size = max(cluster_counts.values()) if cluster_counts else 0
        
        return {
            'clusters_found': True,
            'total_clusters': total_clusters,
            'clustered_errors': clustered_errors,
            'noise_points': noise_count,
            'clustering_percentage': clustering_percentage,
            'largest_cluster_size': largest_cluster_size,
            'cluster_sizes': cluster_counts
        }


# Convenience functions for quick usage
def generate_html_report(results_path: str = "results.json", output_path: str = "analysis_report.html") -> str:
    """Quick function to generate HTML report."""
    generator = ReportGenerator(results_path)
    return generator.generate_html_report(output_path)


def generate_cli_report(results_path: str = "results.json", show_context: bool = True) -> str:
    """Quick function to generate CLI report."""
    generator = ReportGenerator(results_path)
    return generator.generate_cli_report(show_context=show_context)


def print_summary(results_path: str = "results.json") -> None:
    """Quick function to print summary to console."""
    generator = ReportGenerator(results_path)
    generator.print_quick_summary()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate analysis reports")
    parser.add_argument("--results", default="results.json", help="Results JSON file path")
    parser.add_argument("--format", choices=["html", "cli", "json", "text", "summary"], 
                       default="html", help="Report format")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--no-context", action="store_true", help="Hide context in CLI report")
    parser.add_argument("--no-details", action="store_true", help="Hide match details in CLI report")
    
    args = parser.parse_args()
    
    generator = ReportGenerator(args.results)
    
    if args.format == "html":
        output_path = args.output or "analysis_report.html"
        result_path = generator.generate_html_report(output_path)
        print(f"HTML report generated: {result_path}")
        
    elif args.format == "cli":
        report = generator.generate_cli_report(
            show_context=not args.no_context,
            show_details=not args.no_details
        )
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"CLI report saved to: {args.output}")
        else:
            print(report)
            
    elif args.format == "json":
        output_path = args.output or "analysis_summary.json"
        result_path = generator.generate_json_summary(output_path)
        print(f"JSON summary generated: {result_path}")
        
    elif args.format == "text":
        output_path = args.output or "analysis_report.txt"
        result_path = generator.generate_text_report(output_path)
        print(f"Text report generated: {result_path}")
        
    elif args.format == "summary":
        generator.print_quick_summary() 