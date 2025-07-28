#!/usr/bin/env python3
"""
Log Analysis Results Server

This script provides multiple ways to serve and view log analysis results:
1. Static HTML Reports - Beautiful, shareable HTML reports
2. Interactive Web Dashboard - Flask-based web interface with filtering
3. Enhanced CLI Output - Rich command-line reports
4. Quick Summary - Fast overview in terminal
5. Export Options - JSON, text, and HTML exports

Usage Examples:
    # Generate HTML report
    python serve_results.py --format html
    
    # Start interactive web dashboard
    python serve_results.py --format web --port 8080
    
    # Show enhanced CLI report
    python serve_results.py --format cli
    
    # Quick summary
    python serve_results.py --format summary
    
    # Export JSON summary
    python serve_results.py --format json --output analysis_summary.json
"""

import sys
import os
import argparse
import webbrowser
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.report_generator import ReportGenerator, print_summary
    from src.web_server import LogAnalysisWebServer, FLASK_AVAILABLE
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the project root directory.")
    IMPORTS_AVAILABLE = False


def check_results_file(results_path: str) -> bool:
    """Check if results file exists and is readable."""
    if not os.path.exists(results_path):
        print(f"❌ Error: Results file not found: {results_path}")
        print("\nMake sure to run the log analysis first:")
        print("  python src/main.py demo_log.log")
        return False
    
    try:
        with open(results_path, 'r') as f:
            import json
            json.load(f)
        return True
    except (json.JSONDecodeError, Exception) as e:
        print(f"❌ Error: Invalid results file: {e}")
        return False


def serve_html_report(results_path: str, output_path: str, auto_open: bool = True):
    """Generate and optionally open HTML report."""
    print("🔍 Generating HTML Report...")
    
    generator = ReportGenerator(results_path)
    report_path = generator.generate_html_report(output_path)
    
    print(f"✅ HTML report generated: {report_path}")
    
    if auto_open:
        try:
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
            print(f"🌐 Opening report in your default web browser...")
        except Exception as e:
            print(f"⚠️ Could not auto-open browser: {e}")
            print(f"Manually open: file://{os.path.abspath(report_path)}")


def serve_web_dashboard(results_path: str, port: int, host: str, auto_open: bool = True, debug: bool = False):
    """Start interactive web dashboard."""
    if not FLASK_AVAILABLE:
        print("❌ Error: Flask is required for the web dashboard")
        print("Install with: pip install flask")
        return
    
    print("🚀 Starting Interactive Web Dashboard...")
    
    server = LogAnalysisWebServer(results_path, port, host)
    
    if auto_open:
        import threading
        import time
        
        def open_browser():
            time.sleep(1.5)  # Give server time to start
            try:
                webbrowser.open(f"http://{host}:{port}")
            except Exception as e:
                print(f"⚠️ Could not auto-open browser: {e}")
        
        threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        server.run(debug=debug)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")


def serve_cli_report(results_path: str, output_path: str = None, show_context: bool = True, show_details: bool = True):
    """Generate and display CLI report."""
    print("📋 Generating CLI Report...")
    
    generator = ReportGenerator(results_path)
    report = generator.generate_cli_report(show_context=show_context, show_details=show_details)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✅ CLI report saved to: {output_path}")
    else:
        print("\n" + "="*80)
        print(report)


def serve_quick_summary(results_path: str):
    """Display quick summary."""
    generator = ReportGenerator(results_path)
    generator.print_quick_summary()


def export_json_summary(results_path: str, output_path: str):
    """Export JSON summary."""
    print("📊 Generating JSON Summary...")
    
    generator = ReportGenerator(results_path)
    summary_path = generator.generate_json_summary(output_path)
    
    print(f"✅ JSON summary generated: {summary_path}")


def export_text_report(results_path: str, output_path: str):
    """Export text report."""
    print("📄 Generating Text Report...")
    
    generator = ReportGenerator(results_path)
    text_path = generator.generate_text_report(output_path)
    
    print(f"✅ Text report generated: {text_path}")


def interactive_menu(results_path: str):
    """Show interactive menu for format selection."""
    print("\n" + "="*60)
    print("🔍 LOG ANALYSIS RESULTS SERVER")
    print("="*60)
    print(f"Results file: {results_path}")
    
    # Quick check of results
    try:
        generator = ReportGenerator(results_path)
        data = generator.load_results()
        summary = data['summary']
        print(f"📊 {summary['total_errors_found']} errors found in {summary['total_files_processed']} files")
    except Exception as e:
        print(f"⚠️ Warning: Could not load results summary: {e}")
    
    print("\nChoose how to view your results:")
    print("1. 🌐 HTML Report - Beautiful, shareable static report")
    print("2. 🚀 Web Dashboard - Interactive web interface with filtering")
    print("3. 📋 CLI Report - Enhanced command-line output")
    print("4. ⚡ Quick Summary - Fast overview")
    print("5. 📊 Export JSON - Structured data export")
    print("6. 📄 Export Text - Plain text report")
    print("0. ❌ Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (0-6): ").strip()
            
            if choice == '0':
                print("👋 Goodbye!")
                break
            elif choice == '1':
                serve_html_report(results_path, "analysis_report.html")
                break
            elif choice == '2':
                if FLASK_AVAILABLE:
                    port = 5000
                    try:
                        port_input = input(f"Port (default {port}): ").strip()
                        if port_input:
                            port = int(port_input)
                    except ValueError:
                        print("Using default port 5000")
                    serve_web_dashboard(results_path, port, "127.0.0.1")
                else:
                    print("❌ Flask not available. Install with: pip install flask")
                break
            elif choice == '3':
                serve_cli_report(results_path)
                break
            elif choice == '4':
                serve_quick_summary(results_path)
                input("\nPress Enter to continue...")
            elif choice == '5':
                output = input("JSON output path (default: analysis_summary.json): ").strip()
                if not output:
                    output = "analysis_summary.json"
                export_json_summary(results_path, output)
                break
            elif choice == '6':
                output = input("Text output path (default: analysis_report.txt): ").strip()
                if not output:
                    output = "analysis_report.txt"
                export_text_report(results_path, output)
                break
            else:
                print("❌ Invalid choice. Please enter 0-6.")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    """Main entry point."""
    if not IMPORTS_AVAILABLE:
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description="Serve log analysis results in various formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Interactive menu
  %(prog)s --format html                # Generate HTML report
  %(prog)s --format web --port 8080     # Start web dashboard on port 8080
  %(prog)s --format cli --no-context    # CLI report without context
  %(prog)s --format summary             # Quick summary
  %(prog)s --format json --output data.json  # Export JSON summary
  %(prog)s --format text --output report.txt # Export text report
        """
    )
    
    parser.add_argument(
        "--results", 
        default="results.json",
        help="Path to results JSON file (default: results.json)"
    )
    
    parser.add_argument(
        "--format", 
        choices=["html", "web", "cli", "summary", "json", "text"],
        help="Output format (if not specified, shows interactive menu)"
    )
    
    parser.add_argument(
        "--output",
        help="Output file path (for html, cli, json, text formats)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for web dashboard (default: 5000)"
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for web dashboard (default: 127.0.0.1)"
    )
    
    parser.add_argument(
        "--no-context",
        action="store_true",
        help="Hide context in CLI report"
    )
    
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Hide match details in CLI report"
    )
    
    parser.add_argument(
        "--no-auto-open",
        action="store_true",
        help="Don't automatically open browser for HTML/web formats"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run web server in debug mode"
    )
    
    args = parser.parse_args()
    
    # Check if results file exists
    if not check_results_file(args.results):
        sys.exit(1)
    
    # If no format specified, show interactive menu
    if not args.format:
        interactive_menu(args.results)
        return
    
    # Handle each format
    try:
        if args.format == "html":
            output_path = args.output or "analysis_report.html"
            serve_html_report(args.results, output_path, not args.no_auto_open)
            
        elif args.format == "web":
            serve_web_dashboard(
                args.results, 
                args.port, 
                args.host, 
                not args.no_auto_open,
                args.debug
            )
            
        elif args.format == "cli":
            serve_cli_report(
                args.results,
                args.output,
                not args.no_context,
                not args.no_details
            )
            
        elif args.format == "summary":
            serve_quick_summary(args.results)
            
        elif args.format == "json":
            output_path = args.output or "analysis_summary.json"
            export_json_summary(args.results, output_path)
            
        elif args.format == "text":
            output_path = args.output or "analysis_report.txt"
            export_text_report(args.results, output_path)
            
    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 