"""
Retry Aggregator - Processes multiple FAILED - RETRYING lines into summary results.
Instead of showing each individual retry, shows patterns like:
'ROSA HCP installer completion failed with 120 retries'
"""

import re
from typing import List, Dict, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass

from ..models.results import DetectionResult, AnalysisResults


@dataclass
class RetryPattern:
    """Represents a pattern of retries for aggregation."""
    task_name: str
    host: str
    total_retries: int
    first_line: int
    last_line: int
    confidence: float
    original_lines: List[str]


class RetryAggregator:
    """Aggregates multiple FAILED - RETRYING lines into summary results."""
    
    def __init__(self, min_retries: int = 3):
        """
        Initialize retry aggregator.
        
        Args:
            min_retries: Minimum number of retries to aggregate (default 3)
        """
        self.min_retries = min_retries
        self.retry_pattern = re.compile(
            r'FAILED - RETRYING: \[(.*?)\]: (.*?) \((\d+) retries left\)',
            re.IGNORECASE
        )
    
    def aggregate_retries(self, results: AnalysisResults) -> AnalysisResults:
        """
        Process results and aggregate FAILED - RETRYING patterns.
        
        Args:
            results: Original analysis results
            
        Returns:
            Modified results with aggregated retry patterns
        """
        if not results.results:
            return results
        
        # Group retry results by task and host
        retry_groups = self._group_retry_results(results.results)
        
        # Create aggregated results
        aggregated_results = []
        non_retry_results = []
        
        for result in results.results:
            if not self._is_retry_result(result):
                non_retry_results.append(result)
        
        # Add aggregated retry summaries
        for group_key, retry_pattern in retry_groups.items():
            if retry_pattern.total_retries >= self.min_retries:
                summary_result = self._create_retry_summary(retry_pattern)
                aggregated_results.append(summary_result)
        
        # Combine results
        final_results = non_retry_results + aggregated_results
        
        # Update results object
        results.results = final_results
        
        return results
    
    def _group_retry_results(self, results: List[DetectionResult]) -> Dict[str, RetryPattern]:
        """Group retry results by task and host."""
        retry_groups = defaultdict(list)
        
        for result in results:
            if self._is_retry_result(result):
                match = self.retry_pattern.search(result.original_line)
                if match:
                    host, task, retries_left = match.groups()
                    group_key = f"{host}::{task}"
                    retry_groups[group_key].append({
                        'result': result,
                        'retries_left': int(retries_left),
                        'host': host,
                        'task': task
                    })
        
        # Convert groups to RetryPattern objects
        patterns = {}
        for group_key, retry_list in retry_groups.items():
            if len(retry_list) >= self.min_retries:
                # Sort by retries_left (descending) to get the sequence
                retry_list.sort(key=lambda x: x['retries_left'], reverse=True)
                
                first_retry = retry_list[0]
                last_retry = retry_list[-1]
                
                # Calculate total retries from the sequence
                max_retries = first_retry['retries_left']
                min_retries = last_retry['retries_left']
                total_retries = max_retries - min_retries + 1
                
                pattern = RetryPattern(
                    task_name=first_retry['task'],
                    host=first_retry['host'],
                    total_retries=total_retries,
                    first_line=first_retry['result'].line_number,
                    last_line=last_retry['result'].line_number,
                    confidence=max(r['result'].confidence for r in retry_list),
                    original_lines=[r['result'].original_line for r in retry_list]
                )
                patterns[group_key] = pattern
        
        return patterns
    
    def _is_retry_result(self, result: DetectionResult) -> bool:
        """Check if a result is a FAILED - RETRYING line."""
        return (
            'FAILED - RETRYING' in result.original_line and
            'retries left' in result.original_line
        )
    
    def _create_retry_summary(self, pattern: RetryPattern) -> DetectionResult:
        """Create a summary DetectionResult for a retry pattern."""
        # Create a summary line
        summary_line = (
            f"RETRY PATTERN: {pattern.task_name} failed with {pattern.total_retries} retries "
            f"(lines {pattern.first_line}-{pattern.last_line})"
        )
        
        return DetectionResult(
            file_path=pattern.original_lines[0] if pattern.original_lines else "unknown",
            line_number=pattern.first_line,
            confidence=pattern.confidence,
            error_type="retry_pattern_summary",
            original_line=summary_line,
            detector_name="RetryAggregator",
            matched_patterns=["FAILED - RETRYING"],
            context_before=[f"Aggregated from {pattern.total_retries} retry attempts"],
            context_after=[f"Host: {pattern.host}", f"Lines: {pattern.first_line}-{pattern.last_line}"]
        ) 