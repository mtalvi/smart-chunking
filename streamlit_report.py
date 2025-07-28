#!/usr/bin/env python3
"""
Log Error Analysis Report - Clean Professional Dashboard

Provides essential error analysis results in a clean, professional format.
"""

import streamlit as st
import json
import re
from pathlib import Path
from typing import Dict, List, Any

# Page configuration
st.set_page_config(
    page_title="Log Error Analysis Report",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Use dark theme with custom styling
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

# Custom CSS for dark theme with good contrast and error line highlighting
st.markdown("""
<style>
    /* Dark theme with high contrast */
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    
    /* Main content styling */
    .main > div {
        padding-top: 2rem;
        background-color: #0e1117;
    }
    
    /* Metrics styling */
    .stMetric {
        background-color: #262730 !important;
        border: 1px solid #464650 !important;
        border-radius: 6px !important;
        padding: 1rem !important;
        color: #fafafa !important;
    }
    
    .stMetric > div {
        color: #fafafa !important;
    }
    
    .stMetric [data-testid="metric-container"] {
        background-color: #262730 !important;
        color: #fafafa !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        color: #fafafa !important;
    }
    
    .stMetric [data-testid="metric-label"] {
        color: #c9c9c9 !important;
    }
    
    /* Error header styling */
    .error-header {
        background-color: #1f2937 !important;
        color: #f9fafb !important;
        padding: 0.75rem 1rem !important;
        border-radius: 6px 6px 0 0 !important;
        border: 1px solid #374151 !important;
        border-bottom: 2px solid #6b7280 !important;
        margin-bottom: 0 !important;
        font-weight: 600 !important;
    }
    
    /* Text area styling with error line highlighting */
    .stTextArea > div > div > textarea {
        background-color: #1a1a1a !important;
        color: #e5e5e5 !important;
        border: 1px solid #374151 !important;
        border-radius: 0 0 6px 6px !important;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
        font-size: 0.85rem !important;
        line-height: 1.5 !important;
        padding: 1rem !important;
    }
    
    /* Caption styling */
    .caption {
        color: #9ca3af !important;
        font-size: 0.875rem !important;
        margin-bottom: 0.5rem !important;
        font-style: italic !important;
        padding: 0.25rem 0 !important;
    }
    
    /* Title styling */
    h1 {
        color: #f9fafb !important;
        border-bottom: 2px solid #374151 !important;
        padding-bottom: 0.5rem !important;
    }
    
    h2 {
        color: #e5e7eb !important;
        margin-top: 2rem !important;
    }
    
    /* Horizontal rule styling */
    hr {
        border-color: #374151 !important;
    }
    
    /* Custom error line highlighting - this will be applied via JavaScript */
    .error-line-highlight {
        background-color: #dc2626 !important;
        color: #ffffff !important;
        font-weight: bold !important;
        padding: 2px 4px !important;
        border-radius: 3px !important;
    }
</style>
""", unsafe_allow_html=True)

def load_results() -> Dict[str, Any]:
    """Load results from the standard results.json file."""
    results_file = Path("results.json")
    
    if not results_file.exists():
        st.error("No results.json file found. Please run the analysis first:")
        st.code("python -m src.main --input test_logs/ --detector pattern --output results.json")
        st.stop()
    
    try:
        with open(results_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading results.json: {e}")
        st.stop()

def extract_retry_info(original_line: str) -> Dict[str, Any]:
    """Extract retry and grouping information from error lines."""
    info = {"is_grouped": False, "retry_count": 0, "is_workflow": False}
    
    # Check for grouped retry pattern
    grouped_match = re.search(r'\[GROUPED: (\d+) retry attempts\]', original_line)
    if grouped_match:
        info["is_grouped"] = True
        info["retry_count"] = int(grouped_match.group(1))
    
    # Check for workflow grouping
    workflow_match = re.search(r'\[WORKFLOW: (\d+) related error groups, (\d+) total retries\]', original_line)
    if workflow_match:
        info["is_workflow"] = True
        info["workflow_groups"] = int(workflow_match.group(1))
        info["retry_count"] = int(workflow_match.group(2))
    
    return info

def create_summary_section(data: Dict[str, Any]) -> None:
    """Create the vital statistics summary section."""
    st.title("Log Error Analysis Report")
    
    summary = data.get("summary", {})
    results = data.get("results", [])
    
    # Calculate additional metrics
    total_retries = sum(extract_retry_info(r.get("original_line", ""))["retry_count"] for r in results)
    grouped_errors = sum(1 for r in results if extract_retry_info(r.get("original_line", ""))["is_grouped"])
    unique_files_with_errors = len(set(r.get("file_path", "") for r in results))
    avg_confidence = sum(r.get("confidence", 0) for r in results) / len(results) if results else 0
    
    # Display vital statistics in a clean grid
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Errors Found", summary.get("total_errors_found", 0))
        st.metric("Grouped Errors", grouped_errors)
    
    with col2:
        st.metric("Files Processed", summary.get("total_files_processed", 0))
        st.metric("Files with Errors", unique_files_with_errors)
    
    with col3:
        processing_time = summary.get("processing_time", 0)
        st.metric("Processing Time", f"{processing_time:.1f}s")
        st.metric("Average Confidence", f"{avg_confidence:.2f}")

def format_context_display(result: Dict[str, Any]) -> tuple[str, int]:
    """Format the context display and return the error line position."""
    context_before = result.get("context_before", [])
    context_after = result.get("context_after", [])
    original_line = result.get("original_line", "")
    
    # Build the complete context
    lines = []
    
    # Add context before (last 10 lines)
    context_before_filtered = [line for line in context_before[-10:] if line.strip()]
    lines.extend(context_before_filtered)
    
    # Add the original error line (unchanged)
    error_line_position = len(lines)
    lines.append(original_line)
    
    # Add context after (first 10 lines)
    context_after_filtered = [line for line in context_after[:10] if line.strip()]
    lines.extend(context_after_filtered)
    
    return "\n".join(lines), error_line_position

def display_error_results(results: List[Dict[str, Any]]) -> None:
    """Display each error result in a clean format."""
    if not results:
        st.warning("No errors found in the analysis.")
        return
    
    st.header("Error Details")
    
    for i, result in enumerate(results, 1):
        # Extract key information
        error_type = result.get("error_type", "unknown").upper()
        detector_name = result.get("detector_name", "N/A")
        confidence = result.get("confidence", 0)
        file_path = Path(result.get("file_path", "")).name
        line_number = result.get("line_number", "N/A")
        
        # Check for grouping information
        retry_info = extract_retry_info(result.get("original_line", ""))
        
        # Create header with error information
        header_text = f"**Error {i}** - {error_type} | {detector_name} | Confidence: {confidence:.2f}"
        if retry_info["is_grouped"]:
            header_text += f" | Grouped: {retry_info['retry_count']} retries"
        if retry_info.get("is_workflow"):
            header_text += f" | Workflow: {retry_info['workflow_groups']} groups"
        
        st.markdown(f"<div class='error-header'>{header_text}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='caption'>File: {file_path} | Line: {line_number}</div>", unsafe_allow_html=True)
        
        # Format and display context
        context_text, error_line_position = format_context_display(result)
        
        # Use text area for context display
        st.text_area(
            f"Context for Error {i}",
            value=context_text,
            height=400,
            key=f"context_{i}",
            label_visibility="collapsed"
        )
        
        # Add JavaScript for auto-scrolling to error line
        st.markdown(f"""
        <script>
        (function() {{
            const errorIndex = {error_line_position};
            const errorNum = {i};
            
            function scrollToErrorLine() {{
                const textareas = document.querySelectorAll('textarea');
                const targetTextarea = textareas[errorNum - 1]; // Get the textarea for this error
                
                if (targetTextarea && targetTextarea.value) {{
                    // Calculate scroll position to center the error line
                    const lineHeight = parseInt(getComputedStyle(targetTextarea).lineHeight) || 20;
                    const scrollPosition = errorIndex * lineHeight;
                    const centerOffset = targetTextarea.clientHeight / 2;
                    
                    // Scroll to center the error line
                    targetTextarea.scrollTop = Math.max(0, scrollPosition - centerOffset);
                    
                    // Add a subtle highlight to indicate the active textarea
                    targetTextarea.style.border = '2px solid #dc2626';
                    targetTextarea.style.boxShadow = '0 0 10px rgba(220, 38, 38, 0.3)';
                    
                    // Remove highlight after 3 seconds
                    setTimeout(() => {{
                        if (targetTextarea.style) {{
                            targetTextarea.style.border = '1px solid #374151';
                            targetTextarea.style.boxShadow = 'none';
                        }}
                    }}, 3000);
                }}
            }}
            
            // Try multiple times as content loads asynchronously
            setTimeout(scrollToErrorLine, 200);
            setTimeout(scrollToErrorLine, 800);
            setTimeout(scrollToErrorLine, 1500);
        }})();
        </script>
        """, unsafe_allow_html=True)
        
        # Add spacing between errors
        st.markdown("---")
        st.markdown("<br>", unsafe_allow_html=True)

def main():
    """Main application function."""
    # Load data
    data = load_results()
    
    # Create summary section
    create_summary_section(data)
    
    # Add separator
    st.markdown("---")
    
    # Display error results
    results = data.get("results", [])
    display_error_results(results)
    
    # Footer
    st.markdown("---")
    st.caption("Generated by Log Error Extractor with enhanced pattern matching and intelligent deduplication")

if __name__ == "__main__":
    main() 