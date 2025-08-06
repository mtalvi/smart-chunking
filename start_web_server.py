#!/usr/bin/env python3
"""
Start the Smart Chunking Web Server with analysis capabilities.

This script starts a web server that allows users to:
1. Paste logs or upload log files on a landing page
2. Click "Analyze" to run the detection pipeline
3. View interactive results with solutions

Usage:
    python start_web_server.py [--port 5000] [--host 127.0.0.1] [--debug]
"""

import argparse
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.web_server import LogAnalysisWebServer


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Start Smart Chunking Web Server with analysis capabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The web server provides:
- Landing page for pasting logs or uploading files
- Real-time analysis with hybrid detection (--detector hybrid --confidence-threshold 0.7 --verbose)  
- Interactive results dashboard with LLM-powered solutions
- Export capabilities (HTML, JSON, Text)

Access the server at: http://127.0.0.1:5000 (or your specified host:port)
        """
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=5000,
        help="Port to run server on (default: 5000)"
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1", 
        help="Host to bind to (default: 127.0.0.1)"
    )
    
    parser.add_argument(
        "--results-file",
        default="output/analysis.json",
        help="Results file path (default: output/analysis.json)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run in debug mode"
    )
    
    args = parser.parse_args()
    
    # Debug information
    print(f"🚀 Starting Smart Chunking Web Server...")
    print(f"📍 Host: {args.host}")
    print(f"🔌 Port: {args.port}")
    print(f"📄 Results file: {args.results_file}")
    print(f"🐛 Debug mode: {args.debug}")
    print(f"🌐 Landing page will be available at: http://{args.host}:{args.port}")
    
    try:
        # Create and start the web server
        server = LogAnalysisWebServer(
            results_path=args.results_file,
            port=args.port,
            host=args.host
        )
        
        # Verify the server was created correctly
        print(f"✅ Web server initialized successfully")
        print(f"📝 Server will save results to: {server.results_path}")
        
        server.run(debug=args.debug)
        
    except ImportError as e:
        print(f"❌ Error: Missing dependencies: {e}")
        print("Install Flask with: pip install flask")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 