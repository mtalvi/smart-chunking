"""
Lightweight Flask web server for serving log analysis results.

Provides an interactive web interface to browse and filter analysis results
without the complexity of Streamlit.
"""

import json
import os
import tempfile
import threading
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from flask import Flask, render_template_string, request, jsonify, send_from_directory, redirect, url_for, flash
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from src.report_generator import ReportGenerator

# Setup logging for web server
logger = logging.getLogger(__name__)

# Import detection components
from src.detectors import PatternDetector, SemanticDetector, HybridDetector
from src.processors import StreamProcessor, ContextExtractor
from src.models.results import AnalysisResults

# Import solution engine
from src.solutions.engine import HybridSolutionEngine


class LogAnalysisWebServer:
    """Lightweight web server for log analysis with input and results."""
    
    def __init__(self, results_path: str = "analysis.json", port: int = 5000, host: str = "127.0.0.1"):
        """Initialize the web server."""
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the web server. Install with: pip install flask")
        
        self.results_path = results_path
        self.port = port
        self.host = host
        self.app = Flask(__name__)
        self.app.secret_key = 'smart_chunking_log_analysis'  # For flash messages
        self.report_generator = None
        
        # Analysis state tracking
        self.analysis_in_progress = False
        self.analysis_result = None
        
        # Setup routes
        self._setup_routes()
    
    def _clear_previous_analysis(self):
        """Clear previous analysis results and reset state for new analysis."""
        try:
            # Remove existing results file if it exists
            if os.path.exists(self.results_path):
                os.remove(self.results_path)
                logger.info(f"Cleared previous analysis file: {self.results_path}")
            
            # Reset analysis state
            self.analysis_in_progress = False
            self.analysis_result = None
            
            # Reset report generator cache
            if self.report_generator is not None:
                self.report_generator.results_data = None
                logger.info("Cleared report generator cache")
                
        except Exception as e:
            logger.warning(f"Error clearing previous analysis: {e}")
            # Continue anyway - don't block new analysis
    
    def _setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def landing_page():
            """Landing page for log input."""
            return render_template_string(self._get_landing_template())
        
        @self.app.route('/analyze', methods=['POST'])
        def analyze_logs():
            """Analyze uploaded or pasted logs."""
            try:
                # Clear previous analysis results and state
                self._clear_previous_analysis()
                
                # Get input method
                input_method = request.form.get('input_method', 'paste')
                
                if input_method == 'paste':
                    log_content = request.form.get('log_content', '').strip()
                    if not log_content:
                        flash('Please paste some log content to analyze.')
                        return redirect(url_for('landing_page'))
                    
                    # Save to temporary file
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
                    temp_file.write(log_content)
                    temp_file.close()
                    input_path = temp_file.name
                    
                elif input_method == 'upload':
                    if 'log_file' not in request.files:
                        flash('Please select a file to upload.')
                        return redirect(url_for('landing_page'))
                    
                    file = request.files['log_file']
                    if file.filename == '':
                        flash('Please select a file to upload.')
                        return redirect(url_for('landing_page'))
                    
                    if not file.filename.lower().endswith(('.txt', '.log')):
                        flash('Please upload a .txt or .log file.')
                        return redirect(url_for('landing_page'))
                    
                    # Save uploaded file
                    temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
                    file.save(temp_file.name)
                    temp_file.close()
                    input_path = temp_file.name
                
                else:
                    flash('Invalid input method.')
                    return redirect(url_for('landing_page'))
                
                # Start analysis in background
                analysis_thread = threading.Thread(
                    target=self._run_analysis,
                    args=(input_path,),
                    daemon=True
                )
                analysis_thread.start()
                
                # Redirect to progress page
                return redirect(url_for('analysis_progress'))
                
            except Exception as e:
                flash(f'Error processing input: {str(e)}')
                return redirect(url_for('landing_page'))
        
        @self.app.route('/clear')
        def clear_analysis():
            """Clear previous analysis and redirect to landing page."""
            self._clear_previous_analysis()
            flash('Previous analysis cleared. Ready for new analysis.')
            return redirect(url_for('landing_page'))
        
        @self.app.route('/progress')
        def analysis_progress():
            """Show analysis progress."""
            return render_template_string(self._get_progress_template())
        
        @self.app.route('/api/progress')
        def api_progress():
            """API endpoint for analysis progress."""
            return jsonify({
                'in_progress': self.analysis_in_progress,
                'completed': self.analysis_result is not None,
                'error': self.analysis_result.get('error') if isinstance(self.analysis_result, dict) and 'error' in self.analysis_result else None
            })
        
        @self.app.route('/results')
        def results_page():
            """Results dashboard page."""
            if not os.path.exists(self.results_path):
                flash('No analysis results found. Please run an analysis first.')
                return redirect(url_for('landing_page'))
            
            # Initialize report generator if needed
            if self.report_generator is None:
                self.report_generator = ReportGenerator(self.results_path)
            
            return render_template_string(self._get_results_template())
        
        @self.app.route('/api/summary')
        def api_summary():
            """API endpoint for summary data."""
            try:
                if self.report_generator is None:
                    self.report_generator = ReportGenerator(self.results_path)
                
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
                if self.report_generator is None:
                    self.report_generator = ReportGenerator(self.results_path)
                
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
                if self.report_generator is None:
                    self.report_generator = ReportGenerator(self.results_path)
                
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
            temp_file = None
            try:
                # Check if analysis results exist
                if not os.path.exists(self.results_path):
                    return jsonify({'error': 'No analysis results found. Please run an analysis first.'}), 404
                
                # Initialize report generator if needed
                if self.report_generator is None:
                    self.report_generator = ReportGenerator(self.results_path)
                
                # Generate timestamp for unique filenames
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if format == 'html':
                    # Create temporary file for HTML export
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
                    temp_file.close()
                    
                    # Generate HTML report
                    self.report_generator.generate_html_report(temp_file.name)
                    download_name = f'smart_chunking_analysis_{timestamp}.html'
                    
                    return send_from_directory(
                        os.path.dirname(temp_file.name), 
                        os.path.basename(temp_file.name),
                        as_attachment=True, 
                        download_name=download_name,
                        mimetype='text/html'
                    )
                
                elif format == 'json':
                    # Create temporary file for JSON export
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
                    temp_file.close()
                    
                    # Generate JSON summary
                    self.report_generator.generate_json_summary(temp_file.name)
                    download_name = f'smart_chunking_summary_{timestamp}.json'
                    
                    return send_from_directory(
                        os.path.dirname(temp_file.name), 
                        os.path.basename(temp_file.name),
                        as_attachment=True, 
                        download_name=download_name,
                        mimetype='application/json'
                    )
                
                elif format == 'text':
                    # Create temporary file for text export
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
                    temp_file.close()
                    
                    # Generate text report
                    self.report_generator.generate_text_report(temp_file.name)
                    download_name = f'smart_chunking_report_{timestamp}.txt'
                    
                    return send_from_directory(
                        os.path.dirname(temp_file.name), 
                        os.path.basename(temp_file.name),
                        as_attachment=True, 
                        download_name=download_name,
                        mimetype='text/plain'
                    )
                
                else:
                    return jsonify({'error': f'Unsupported export format: {format}. Supported formats: html, json, text'}), 400
                    
            except FileNotFoundError as e:
                logger.error(f"Export failed - file not found: {e}")
                return jsonify({'error': 'Analysis results file not found. Please run an analysis first.'}), 404
                
            except Exception as e:
                logger.error(f"Export failed for format {format}: {e}")
                return jsonify({'error': f'Export failed: {str(e)}'}), 500
                
            finally:
                # Schedule cleanup of temporary file after a delay
                if temp_file and os.path.exists(temp_file.name):
                    def cleanup_temp_file():
                        try:
                            time.sleep(5)  # Wait 5 seconds to ensure download completed
                            if os.path.exists(temp_file.name):
                                os.remove(temp_file.name)
                                logger.info(f"Cleaned up temporary export file: {temp_file.name}")
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to cleanup temp file {temp_file.name}: {cleanup_error}")
                    
                    # Run cleanup in background thread
                    cleanup_thread = threading.Thread(target=cleanup_temp_file, daemon=True)
                    cleanup_thread.start()
    
    def _run_analysis(self, input_path: str):
        """Run analysis in background thread."""
        try:
            self.analysis_in_progress = True
            self.analysis_result = None
            
            # Create detector (hybrid with specified parameters)
            detector = HybridDetector(
                confidence_threshold=0.7,
                config_path="config/patterns.yaml"
            )
            
            # Create context extractor
            context_extractor = ContextExtractor(
                context_before=5,
                context_after=10
            )
            
            # Create stream processor
            processor = StreamProcessor(
                detector=detector,
                context_extractor=context_extractor,
                parallel_workers=None  # Auto-detect
            )
            
            # Process the input file
            logger.info(f"Processing user input file: {input_path}")
            results = processor.process_files([input_path], show_progress=False)
            logger.info(f"Analysis completed. Found {len(results.results) if results.results else 0} errors.")
            
            # Deduplicate results
            if results.results:
                original_count = len(results.results)
                results.deduplicate()
                dedup_count = len(results.results)
                if original_count != dedup_count:
                    logger.info(f"Deduplicated {original_count - dedup_count} similar results")
            
            # Apply retry aggregation to reduce noise from multiple RETRYING lines
            if results.results:
                try:
                    logger.info("Aggregating retry patterns...")
                    from src.processors.retry_aggregator import RetryAggregator
                    retry_aggregator = RetryAggregator(min_retries=1)
                    results = retry_aggregator.aggregate_retries(results)
                    logger.info("Retry aggregation completed")
                except Exception as e:
                    logger.warning(f"Error during retry aggregation: {e}")
            
            # Add solutions using the solution engine
            solution_engine = HybridSolutionEngine(enable_llm=True)
            
            # Process each result through the solution engine
            for result in results.results:
                # Update file path to be more user-friendly for uploaded/pasted content
                if result.file_path.startswith('/tmp/'):
                    result.file_path = "User Input (uploaded/pasted content)"
                
                # Convert result to dict format expected by solution engine
                result_dict = {
                    'original_line': result.original_line,
                    'error_type': result.error_type,
                    'confidence': result.confidence,
                    'file_path': result.file_path,
                    'line_number': result.line_number,
                    'matched_patterns': getattr(result, 'matched_patterns', []),
                    'matched_semantic_phrases': getattr(result, 'matched_semantic_phrases', []),
                    'context_before': getattr(result, 'context_before', []),
                    'context_after': getattr(result, 'context_after', [])
                }
                
                solutions = solution_engine.find_solutions(result_dict)
                result.solutions = solutions
                
                # Add solution metadata
                if solutions:
                    result.solution_source = 'hybrid'
                    result.solution_confidence = max(s.get('confidence', 0) for s in solutions)
                else:
                    result.solution_source = 'none'
                    result.solution_confidence = 0.0
            
            # Save results to JSON
            results.to_json(Path(self.results_path))
            
            # Clean up temporary file
            try:
                os.unlink(input_path)
            except:
                pass  # Ignore cleanup errors
            
            self.analysis_result = {'status': 'completed'}
            
        except Exception as e:
            self.analysis_result = {'error': str(e)}
        finally:
            self.analysis_in_progress = False
    
    def _get_landing_template(self) -> str:
        """Get the landing page HTML template."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Chunking - Log Analysis</title>
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 800px;
            width: 90%;
            margin: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .header h1 {
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        
        .header p {
            color: #666;
            font-size: 1.2em;
        }
        
        .input-section {
            margin-bottom: 30px;
        }
        
        .input-tabs {
            display: flex;
            border-bottom: 2px solid #eee;
            margin-bottom: 20px;
        }
        
        .tab-button {
            flex: 1;
            padding: 15px;
            background: none;
            border: none;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
            border-bottom: 3px solid transparent;
        }
        
        .tab-button.active {
            color: #3498db;
            border-bottom-color: #3498db;
            background: #f8f9fa;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }
        
        .form-group textarea {
            width: 100%;
            min-height: 300px;
            padding: 15px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            resize: vertical;
            transition: border-color 0.3s;
        }
        
        .form-group textarea:focus {
            outline: none;
            border-color: #3498db;
        }
        
        .form-group input[type="file"] {
            width: 100%;
            padding: 15px;
            border: 2px dashed #ddd;
            border-radius: 8px;
            background: #f8f9fa;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .form-group input[type="file"]:hover {
            border-color: #3498db;
            background: #e3f2fd;
        }
        
        .analyze-button {
            width: 100%;
            padding: 18px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .analyze-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        
        .analyze-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .features {
            margin-top: 40px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        
        .feature {
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        
        .feature-icon {
            font-size: 2em;
            margin-bottom: 10px;
        }
        
        .feature h3 {
            color: #2c3e50;
            margin-bottom: 8px;
        }
        
        .feature p {
            color: #666;
            font-size: 0.9em;
        }
        
        .flash-messages {
            margin-bottom: 20px;
        }
        
        .flash-message {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .flash-message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .flash-message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
                margin: 10px;
            }
            
            .header h1 {
                font-size: 2em;
            }
            
            .features {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Smart Chunking</h1>
            <p>Intelligent Log Analysis with LLM-Powered Solutions</p>
        </div>
        
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="flash-messages">
                    {% for message in messages %}
                        <div class="flash-message error">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="input-section">
                <div class="input-tabs">
                    <button type="button" class="tab-button active" onclick="switchTab('paste')">
                        📝 Paste Logs
                    </button>
                    <button type="button" class="tab-button" onclick="switchTab('upload')">
                        📁 Upload File
                    </button>
                </div>
                
                <div id="paste-tab" class="tab-content active">
                    <input type="hidden" name="input_method" value="paste">
                    <div class="form-group">
                        <label for="log_content">Paste your log content:</label>
                        <textarea 
                            name="log_content" 
                            id="log_content" 
                            placeholder="Paste your Ansible logs, system logs, or any text logs here...&#10;&#10;Example:&#10;2024-01-15 10:30:45 TASK [deploy-app : Copy application files] ***&#10;fatal: [web-server-01]: UNREACHABLE! => {&quot;changed&quot;: false, &quot;msg&quot;: &quot;Failed to connect to the host via ssh&quot;}"
                        ></textarea>
                    </div>
                </div>
                
                <div id="upload-tab" class="tab-content">
                    <input type="hidden" name="input_method" value="upload">
                    <div class="form-group">
                        <label for="log_file">Upload a log file (.txt or .log):</label>
                        <input type="file" name="log_file" id="log_file" accept=".txt,.log">
                    </div>
                </div>
            </div>
            
            <button type="submit" class="analyze-button" id="analyze-btn">
                🚀 Analyze Logs
            </button>
        </form>
        
        <div class="features">
            <div class="feature">
                <div class="feature-icon">🎯</div>
                <h3>95% Accuracy</h3>
                <p>Hybrid ML detection combining pattern, semantic, and statistical analysis</p>
            </div>
            <div class="feature">
                <div class="feature-icon">⚡</div>
                <h3>Instant Solutions</h3>
                <p>Pattern-based solutions with LLM fallback for unknown errors</p>
            </div>
            <div class="feature">
                <div class="feature-icon">🤖</div>
                <h3>AI-Powered</h3>
                <p>Intelligent troubleshooting guidance for every detected error</p>
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab-button').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(tabName + '-tab').classList.add('active');
        }
        
        // Form validation
        document.querySelector('form').addEventListener('submit', function(e) {
            const method = document.querySelector('input[name="input_method"]').value;
            
            if (method === 'paste') {
                const content = document.getElementById('log_content').value.trim();
                if (!content) {
                    e.preventDefault();
                    alert('Please paste some log content to analyze.');
                    return;
                }
            } else if (method === 'upload') {
                const file = document.getElementById('log_file').files[0];
                if (!file) {
                    e.preventDefault();
                    alert('Please select a file to upload.');
                    return;
                }
            }
            
            // Disable button and show loading
            const btn = document.getElementById('analyze-btn');
            btn.disabled = true;
            btn.innerHTML = '⏳ Analyzing...';
        });
    </script>
</body>
</html>"""

    def _get_progress_template(self) -> str:
        """Get the progress page HTML template."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analysis in Progress - Smart Chunking</title>
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 600px;
            width: 90%;
            margin: 20px;
            text-align: center;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .status {
            font-size: 1.2em;
            margin: 20px 0;
            color: #2c3e50;
        }
        
        .progress-steps {
            text-align: left;
            margin: 30px 0;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
        }
        
        .step {
            padding: 8px 0;
            color: #666;
        }
        
        .step.current {
            color: #3498db;
            font-weight: bold;
        }
        
        .step.completed {
            color: #27ae60;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            display: none;
        }
        
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            display: none;
        }
        
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            margin-top: 20px;
            transition: background 0.3s;
        }
        
        .btn:hover {
            background: #2980b9;
        }
        
        .btn.success {
            background: #27ae60;
        }
        
        .btn.success:hover {
            background: #229954;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Analyzing Your Logs</h1>
        
        <div id="loading-section">
            <div class="spinner"></div>
            <div class="status" id="status">Starting analysis...</div>
            
            <div class="progress-steps">
                <div class="step current" id="step1">🔍 Initializing detection engine...</div>
                <div class="step" id="step2">📊 Processing log content...</div>
                <div class="step" id="step3">🎯 Running hybrid detection...</div>
                <div class="step" id="step4">🤖 Generating AI solutions...</div>
                <div class="step" id="step5">💾 Saving results...</div>
            </div>
        </div>
        
        <div class="error-message" id="error-message"></div>
        <div class="success-message" id="success-message">
            ✅ Analysis completed successfully!
            <br><br>
            <a href="/results" class="btn success">View Results</a>
        </div>
        
        <a href="/" class="btn">← Start New Analysis</a>
    </div>

    <script>
        let stepIndex = 0;
        const steps = ['step1', 'step2', 'step3', 'step4', 'step5'];
        const stepTexts = [
            '🔍 Initializing detection engine...',
            '📊 Processing log content...',
            '🎯 Running hybrid detection...',
            '🤖 Generating AI solutions...',
            '💾 Saving results...'
        ];
        
        function updateStep() {
            // Mark current step as completed
            if (stepIndex > 0) {
                document.getElementById(steps[stepIndex - 1]).classList.remove('current');
                document.getElementById(steps[stepIndex - 1]).classList.add('completed');
            }
            
            // Update current step
            if (stepIndex < steps.length) {
                document.getElementById(steps[stepIndex]).classList.add('current');
                document.getElementById('status').textContent = stepTexts[stepIndex];
                stepIndex++;
            }
        }
        
        function checkProgress() {
            fetch('/api/progress')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        // Show error
                        document.getElementById('loading-section').style.display = 'none';
                        document.getElementById('error-message').style.display = 'block';
                        document.getElementById('error-message').innerHTML = 
                            '❌ Analysis failed: ' + data.error + 
                            '<br><br><a href="/" class="btn">Try Again</a>';
                    } else if (data.completed) {
                        // Show success
                        document.getElementById('loading-section').style.display = 'none';
                        document.getElementById('success-message').style.display = 'block';
                    } else if (data.in_progress) {
                        // Continue polling
                        setTimeout(checkProgress, 1000);
                        
                        // Update steps periodically
                        if (Math.random() < 0.3) {
                            updateStep();
                        }
                    }
                })
                .catch(error => {
                    console.error('Error checking progress:', error);
                    setTimeout(checkProgress, 2000);
                });
        }
        
        // Start progress checking
        setTimeout(checkProgress, 1000);
        
        // Simulate step progression
        setTimeout(() => updateStep(), 2000);
        setTimeout(() => updateStep(), 5000);
        setTimeout(() => updateStep(), 8000);
        setTimeout(() => updateStep(), 12000);
    </script>
</body>
</html>"""

    def _get_results_template(self) -> str:
        """Get the results dashboard HTML template."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analysis Results - Smart Chunking</title>
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
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        
        .header-actions {
            display: flex;
            gap: 10px;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            display: inline-block;
            transition: background-color 0.2s;
        }
        
        .btn-primary {
            background: #3498db;
            color: white;
        }
        
        .btn-primary:hover {
            background: #2980b9;
        }
        
        .btn-success {
            background: #27ae60;
            color: white;
        }
        
        .btn-success:hover {
            background: #229954;
        }
        
        .btn-secondary {
            background: #95a5a6;
            color: white;
        }
        
        .btn-secondary:hover {
            background: #7f8c8d;
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
        
        .solutions-section {
            margin-top: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            border-left: 4px solid #28a745;
        }

        .solutions-section h4 {
            color: #28a745;
            margin: 0 0 10px 0;
            font-size: 1em;
        }

        .solution-item {
            margin-bottom: 15px;
            padding: 10px;
            background: white;
            border-radius: 5px;
            border: 1px solid #dee2e6;
        }

        .solution-item .source-badge {
            background: #17a2b8;
            color: white;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 0.75em;
        }

        .solution-item .confidence-badge {
            background: #ffc107;
            color: #212529;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 0.75em;
            margin-left: 5px;
        }

        .solution-item .category-time {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 8px;
        }

        .solution-item ol {
            margin: 0;
            color: #495057;
        }

        .solution-item li {
            margin-bottom: 5px;
        }

        .no-solutions {
            margin-top: 15px;
            padding: 10px;
            background: #fff3cd;
            border-radius: 5px;
            border-left: 4px solid #ffc107;
            color: #856404;
        }
        
        .log-description {
            margin-bottom: 15px;
            padding: 12px;
            background: #e8f4fd;
            border-left: 4px solid #3498db;
            border-radius: 5px;
        }

        .log-description h5 {
            color: #2980b9;
            margin: 0 0 8px 0;
            font-size: 0.9em;
        }

        .log-description p {
            margin: 0;
            color: #34495e;
            font-size: 0.9em;
            line-height: 1.4;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header {
                flex-direction: column;
                gap: 15px;
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
            <div>
                <h1>🔍 Analysis Results</h1>
                <p>Interactive log analysis dashboard</p>
            </div>
            <div class="header-actions">
                <a href="/" class="btn btn-primary">← New Analysis</a>
            </div>
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
                
                // Build solutions HTML
                let solutionsHtml = '';
                if (result.solutions && result.solutions.length > 0) {
                    solutionsHtml = '<div class="solutions-section">';
                    solutionsHtml += `<h4>🔧 Solutions (${result.solutions.length})</h4>`;
                    
                    // Add log description if available (from first solution since all solutions share the same description)
                    const logDescription = result.solutions[0].log_description;
                    if (logDescription && logDescription.trim()) {
                        solutionsHtml += `
                            <div class="log-description" style="margin-bottom: 15px; padding: 12px; background: #e8f4fd; border-left: 4px solid #3498db; border-radius: 5px;">
                                <h5 style="color: #2980b9; margin: 0 0 8px 0; font-size: 0.9em;">📋 Log Context Analysis</h5>
                                <p style="margin: 0; color: #34495e; font-size: 0.9em; line-height: 1.4;">${escapeHtml(logDescription)}</p>
                            </div>
                        `;
                    }
                    
                    result.solutions.forEach((solution, solIndex) => {
                        const sourceIcon = solution.type === 'llm_generated' ? '🤖' : '📋';
                        const sourceText = solution.type === 'llm_generated' ? 'AI Generated' : 'Pattern Based';
                        
                        solutionsHtml += `
                            <div class="solution-item">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                    <strong style="color: #2c3e50;">${solution.title}</strong>
                                    <div>
                                        <span class="source-badge">${sourceIcon} ${sourceText}</span>
                                        <span class="confidence-badge">
                                            ${(solution.confidence * 100).toFixed(0)}% confidence
                                        </span>
                                    </div>
                                </div>
                                <div class="category-time">
                                    Category: ${solution.category || 'General'} | 
                                    Est. Time: ${solution.estimated_fix_time || 'Unknown'}
                                </div>
                        `;
                        
                        if (solution.steps && solution.steps.length > 0) {
                            solutionsHtml += '<ol>';
                            solution.steps.forEach(step => {
                                // Remove "Step X:" prefix to avoid duplication with ordered list numbering
                                const cleanStep = step.replace(/^Step \d+:\s*/, '');
                                solutionsHtml += `<li style="margin-bottom: 5px;">${escapeHtml(cleanStep)}</li>`;
                            });
                            solutionsHtml += '</ol>';
                        }
                        
                        solutionsHtml += '</div>';
                    });
                    
                    solutionsHtml += '</div>';
                } else if (result.solution_source === 'none') {
                    solutionsHtml = '<div class="no-solutions">⚠️ No solutions available for this error</div>';
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
                        ${solutionsHtml}
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
            // Show loading indicator
            const button = event.target;
            const originalText = button.textContent;
            button.textContent = `Exporting ${format.toUpperCase()}...`;
            button.disabled = true;
            
            try {
                const response = await fetch(`/export/${format}`);
                
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    
                    // Extract filename from Content-Disposition header or use fallback
                    let filename = `smart_chunking_export_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.${format}`;
                    const contentDisposition = response.headers.get('Content-Disposition');
                    if (contentDisposition) {
                        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                        if (filenameMatch) {
                            filename = filenameMatch[1];
                        }
                    }
                    
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                    
                    // Show success message
                    const successMsg = document.createElement('div');
                    successMsg.className = 'alert alert-success';
                    successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1000; padding: 10px 20px; background: #d4edda; color: #155724; border: 1px solid #c3e6cb; border-radius: 4px;';
                    successMsg.textContent = `✅ ${format.toUpperCase()} export completed successfully!`;
                    document.body.appendChild(successMsg);
                    
                    // Remove success message after 3 seconds
                    setTimeout(() => {
                        if (successMsg.parentNode) {
                            document.body.removeChild(successMsg);
                        }
                    }, 3000);
                    
                } else {
                    // Handle error response
                    const errorData = await response.json();
                    throw new Error(errorData.error || `Export failed with status ${response.status}`);
                }
                
            } catch (error) {
                console.error('Export error:', error);
                
                // Show error message
                const errorMsg = document.createElement('div');
                errorMsg.className = 'alert alert-error';
                errorMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1000; padding: 10px 20px; background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; border-radius: 4px; max-width: 400px;';
                errorMsg.textContent = `❌ Export failed: ${error.message}`;
                document.body.appendChild(errorMsg);
                
                // Remove error message after 5 seconds
                setTimeout(() => {
                    if (errorMsg.parentNode) {
                        document.body.removeChild(errorMsg);
                    }
                }, 5000);
                
            } finally {
                // Restore button state
                button.textContent = originalText;
                button.disabled = false;
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
        print(f"Starting Smart Chunking Web Server...")
        print(f"Landing page will be available at: http://{self.host}:{self.port}")
        print(f"Results will be saved to: {self.results_path}")
        print(f"Press Ctrl+C to stop the server")
        
        self.app.run(host=self.host, port=self.port, debug=debug)


def start_web_server(results_path: str = "results.json", port: int = 5000, host: str = "127.0.0.1", debug: bool = False):
    """Start the web server with the given configuration."""
    server = LogAnalysisWebServer(results_path, port, host)
    server.run(debug)