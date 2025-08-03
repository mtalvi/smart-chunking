"""
Statistical anomaly detector for identifying unusual patterns in logs without ML training.
"""

import re
from typing import Optional, List, Dict, Tuple
from collections import defaultdict
from datetime import datetime
import statistics
import numpy as np
from functools import lru_cache

from src.detectors.base import BaseDetector
from src.models.results import DetectionResult


class StatisticalAnomalyDetector(BaseDetector):
    """Statistical anomaly detector using statistical methods to identify unusual patterns."""
    
    def __init__(self, confidence_threshold: float = 0.8, z_threshold: float = 3.0,
                 min_samples: int = 5):
        """
        Initialize the statistical anomaly detector.
        
        Args:
            confidence_threshold: Minimum confidence score for detection
            z_threshold: Z-score threshold for anomaly detection
            min_samples: Minimum number of samples needed for baseline statistics
        """
        super().__init__(confidence_threshold)
        self.name = "StatisticalDetector"
        
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        
        # Statistical tracking structures
        self.task_durations = defaultdict(list)
        self.task_patterns = defaultdict(int)
        self.baseline_stats = {}
        self.error_frequencies = defaultdict(int)
        self.line_length_stats = defaultdict(list)
        self.timestamp_intervals = []
        
        # Pattern regex for various log elements
        self.patterns = {
            'ansible_task': re.compile(r"TASK \[(.*?)\].*?(\d+):(\d+):(\d+(?:\.\d+)?)", re.IGNORECASE),
            'ansible_play': re.compile(r"PLAY \[(.*?)\]", re.IGNORECASE),
            'timestamp': re.compile(r"(\d{4}-\d{2}-\d{2}[\s|T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", re.IGNORECASE),
            'error_keywords': re.compile(r"\b(error|fail|exception|timeout|refused|denied|unreachable|fatal|critical|abort)\b", re.IGNORECASE),
            'retry_pattern': re.compile(r"retrying.*?(\d+).*?retries?\s+left", re.IGNORECASE),
            'percentage': re.compile(r"(\d+(?:\.\d+)?)%", re.IGNORECASE),
            'memory_size': re.compile(r"(\d+(?:\.\d+)?)\s*(kb|mb|gb|tb|bytes?)", re.IGNORECASE),
            'ip_address': re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
            'duration': re.compile(r"(\d+(?:\.\d+)?)\s*(ms|sec|min|hr|hours?|minutes?|seconds?)", re.IGNORECASE)
        }
    
    def setup(self) -> None:
        """Setup method - no special initialization needed for statistical detection."""
        print("Statistical anomaly detector initialized")
        print(f"Z-score threshold: {self.z_threshold}")
        print(f"Minimum samples for baseline: {self.min_samples}")
    
    def should_detect(self, line: str) -> bool:
        """Determine if line should be analyzed for statistical anomalies."""
        line_clean = line.strip()
        
        # Skip empty lines
        if not line_clean:
            return False
        
        # Skip very short lines
        if len(line_clean.split()) < 3:
            return False
        
        # Process lines that have:
        # 1. Potential timing information
        # 2. Error indicators
        # 3. Resource usage metrics
        # 4. Task/operation indicators
        
        has_timing = self.patterns['timestamp'].search(line) or self.patterns['duration'].search(line)
        has_errors = self.patterns['error_keywords'].search(line)
        has_metrics = (self.patterns['percentage'].search(line) or 
                      self.patterns['memory_size'].search(line))
        has_tasks = (self.patterns['ansible_task'].search(line) or 
                    self.patterns['ansible_play'].search(line))
        
        return has_timing or has_errors or has_metrics or has_tasks
    
    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Detect statistical anomalies in log lines.
        
        Args:
            line: The log line to analyze
            line_number: Line number in the file (1-indexed)
            file_path: Path to the file being analyzed
            
        Returns:
            DetectionResult if an anomaly is detected, None otherwise
        """
        if not self.should_detect(line):
            return None
        
        # Update statistics for this line
        self._update_statistics(line, line_number)
        
        # Check for various types of anomalies
        anomaly_results = []
        
        # 1. Check task duration anomalies
        duration_anomaly = self._check_duration_anomaly(line)
        if duration_anomaly:
            anomaly_results.append(duration_anomaly)
        
        # 2. Check error frequency anomalies
        frequency_anomaly = self._check_error_frequency_anomaly(line)
        if frequency_anomaly:
            anomaly_results.append(frequency_anomaly)
        
        # 3. Check line length anomalies
        length_anomaly = self._check_line_length_anomaly(line, file_path)
        if length_anomaly:
            anomaly_results.append(length_anomaly)
        
        # 4. Check retry pattern anomalies
        retry_anomaly = self._check_retry_pattern_anomaly(line)
        if retry_anomaly:
            anomaly_results.append(retry_anomaly)
        
        # Return the most significant anomaly
        if anomaly_results:
            # Sort by confidence and return the highest
            best_anomaly = max(anomaly_results, key=lambda x: x['confidence'])
            
            if best_anomaly['confidence'] >= self.confidence_threshold:
                result = DetectionResult(
                    file_path=file_path,
                    line_number=line_number,
                    confidence=best_anomaly['confidence'],
                    error_type=best_anomaly['error_type'],
                    original_line=line.strip(),
                    detector_name=self.name,
                    matched_patterns=[best_anomaly['anomaly_type']],
                    match_details={
                        'anomaly_type': best_anomaly['anomaly_type'],
                        'anomaly_description': best_anomaly['description'],
                        'statistical_data': best_anomaly['stats'],
                        'z_score': best_anomaly.get('z_score', 0),
                        'detection_method': 'statistical_analysis'
                    }
                )
                return result
        
        return None
    
    def _update_statistics(self, line: str, line_number: int) -> None:
        """Update running statistics with information from the current line."""
        # Update task duration statistics
        task_name, duration = self._parse_task_duration(line)
        if task_name and duration:
            self.task_durations[task_name].append(duration)
            self._update_baseline(task_name, duration)
        
        # Update error frequency statistics
        if self.patterns['error_keywords'].search(line):
            error_type = self._extract_error_type(line)
            self.error_frequencies[error_type] += 1
        
        # Update line length statistics
        file_key = "global"  # Could be made file-specific if needed
        self.line_length_stats[file_key].append(len(line))
    
    def _parse_task_duration(self, line: str) -> Tuple[Optional[str], Optional[float]]:
        """Extract task name and duration from Ansible task completion lines."""
        match = self.patterns['ansible_task'].search(line)
        if match:
            task_name = match.group(1)
            hours = int(match.group(2))
            minutes = int(match.group(3))
            seconds = float(match.group(4))
            duration = hours * 3600 + minutes * 60 + seconds
            return task_name, duration
        return None, None
    
    def _update_baseline(self, task_name: str, duration: float) -> None:
        """Update running statistics for tasks."""
        if len(self.task_durations[task_name]) >= self.min_samples:
            durations = self.task_durations[task_name]
            
            # Keep only recent samples to adapt to changing conditions
            if len(durations) > 100:  
                durations = durations[-100:]
                self.task_durations[task_name] = durations
            
            self.baseline_stats[task_name] = {
                'mean': statistics.mean(durations),
                'stdev': statistics.stdev(durations) if len(durations) > 1 else 0,
                'median': statistics.median(durations),
                'p95': np.percentile(durations, 95),
                'p99': np.percentile(durations, 99),
                'count': len(durations)
            }
    
    def _check_duration_anomaly(self, line: str) -> Optional[Dict]:
        """Check if a task duration is anomalous."""
        task_name, duration = self._parse_task_duration(line)
        
        if not task_name or not duration:
            return None
        
        if task_name not in self.baseline_stats:
            return None
        
        stats = self.baseline_stats[task_name]
        if stats['stdev'] == 0:
            return None
        
        z_score = (duration - stats['mean']) / stats['stdev']
        
        if abs(z_score) > self.z_threshold:
            anomaly_type = "slow_task" if z_score > 0 else "fast_task"
            confidence = min(0.95, (abs(z_score) - self.z_threshold) / 5.0 + 0.7)
            
            return {
                'anomaly_type': f"duration_{anomaly_type}",
                'confidence': confidence,
                'error_type': f"statistical_{anomaly_type}",
                'description': f"Task '{task_name}' duration ({duration:.1f}s) is {abs(z_score):.2f} standard deviations from normal",
                'z_score': z_score,
                'stats': {
                    'duration': duration,
                    'baseline_mean': stats['mean'],
                    'baseline_stdev': stats['stdev'],
                    'z_score': z_score
                }
            }
        
        return None
    
    def _extract_error_type(self, line: str) -> str:
        """Extract a generalized error type from the line."""
        line_lower = line.lower()
        
        # Priority-based error type extraction
        error_types = [
            ('timeout', ['timeout', 'timed out']),
            ('connection', ['connection', 'connect', 'refused', 'unreachable']),
            ('permission', ['permission', 'denied', 'access denied', 'forbidden']),
            ('authentication', ['authentication', 'auth', 'login', 'credential']),
            ('resource', ['memory', 'disk', 'space', 'resource', 'allocation']),
            ('configuration', ['config', 'syntax', 'parse', 'invalid']),
            ('network', ['network', 'host', 'dns', 'resolve']),
            ('generic', ['error', 'fail', 'exception', 'fatal', 'critical'])
        ]
        
        for error_type, keywords in error_types:
            if any(keyword in line_lower for keyword in keywords):
                return error_type
        
        return 'unknown'
    
    def _check_error_frequency_anomaly(self, line: str) -> Optional[Dict]:
        """Check if error frequency is anomalous."""
        if not self.patterns['error_keywords'].search(line):
            return None
        
        error_type = self._extract_error_type(line)
        current_frequency = self.error_frequencies[error_type]
        
        # Need at least some history to detect anomalies
        if current_frequency < 3:
            return None
        
        # Calculate frequency rate (errors per processing session)
        # This is a simplified approach - could be enhanced with time-based analysis
        all_frequencies = list(self.error_frequencies.values())
        
        if len(all_frequencies) < 3:
            return None
        
        mean_freq = statistics.mean(all_frequencies)
        stdev_freq = statistics.stdev(all_frequencies) if len(all_frequencies) > 1 else 1
        
        if stdev_freq > 0:
            z_score = (current_frequency - mean_freq) / stdev_freq
            
            if z_score > self.z_threshold:
                confidence = min(0.9, (z_score - self.z_threshold) / 3.0 + 0.7)
                
                return {
                    'anomaly_type': 'high_error_frequency',
                    'confidence': confidence,
                    'error_type': 'statistical_frequent_errors',
                    'description': f"High frequency of {error_type} errors ({current_frequency} occurrences)",
                    'z_score': z_score,
                    'stats': {
                        'error_type': error_type,
                        'frequency': current_frequency,
                        'baseline_mean': mean_freq,
                        'baseline_stdev': stdev_freq
                    }
                }
        
        return None
    
    def _check_line_length_anomaly(self, line: str, file_path: str) -> Optional[Dict]:
        """Check if line length is anomalous."""
        file_key = "global"
        line_length = len(line)
        
        lengths = self.line_length_stats[file_key]
        
        if len(lengths) < self.min_samples:
            return None
        
        mean_length = statistics.mean(lengths)
        stdev_length = statistics.stdev(lengths) if len(lengths) > 1 else 1
        
        if stdev_length > 0:
            z_score = (line_length - mean_length) / stdev_length
            
            if abs(z_score) > self.z_threshold:
                anomaly_type = "long_line" if z_score > 0 else "short_line"
                confidence = min(0.85, (abs(z_score) - self.z_threshold) / 4.0 + 0.6)
                
                return {
                    'anomaly_type': f"line_length_{anomaly_type}",
                    'confidence': confidence,
                    'error_type': f"statistical_{anomaly_type}",
                    'description': f"Line length ({line_length} chars) is {abs(z_score):.2f} standard deviations from normal",
                    'z_score': z_score,
                    'stats': {
                        'line_length': line_length,
                        'baseline_mean': mean_length,
                        'baseline_stdev': stdev_length
                    }
                }
        
        return None
    
    def _check_retry_pattern_anomaly(self, line: str) -> Optional[Dict]:
        """Check for unusual retry patterns."""
        retry_match = self.patterns['retry_pattern'].search(line)
        
        if retry_match:
            retries_left = int(retry_match.group(1))
            
            # Flag unusually high retry counts as anomalous
            if retries_left > 50:  # Configurable threshold
                confidence = min(0.9, (retries_left - 50) / 100.0 + 0.7)
                
                return {
                    'anomaly_type': 'excessive_retries',
                    'confidence': confidence,
                    'error_type': 'statistical_excessive_retries',
                    'description': f"Excessive retry attempts detected ({retries_left} retries remaining)",
                    'stats': {
                        'retries_left': retries_left,
                        'threshold': 50
                    }
                }
        
        return None
    
    @lru_cache(maxsize=1000)
    def get_confidence(self, line: str) -> float:
        """Calculate confidence score for statistical anomaly detection."""
        # This is a simplified confidence calculation
        # In practice, this would run the full detection pipeline
        if not self.should_detect(line):
            return 0.0
        
        # Quick heuristic-based confidence estimation
        confidence = 0.0
        
        # Check for obvious anomaly indicators
        if self.patterns['error_keywords'].search(line):
            confidence += 0.3
        
        if self.patterns['retry_pattern'].search(line):
            confidence += 0.2
        
        # Length-based heuristic
        line_length = len(line)
        if line_length > 500 or line_length < 20:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    @lru_cache(maxsize=1000)
    def get_error_type(self, line: str) -> str:
        """Determine error type based on statistical analysis."""
        if self.patterns['error_keywords'].search(line):
            error_type = self._extract_error_type(line)
            return f"statistical_{error_type}"
        
        return "statistical_anomaly"
    
    def batch_detect(self, lines: List[tuple], file_path: str) -> List[DetectionResult]:
        """Batch detection for statistical anomalies."""
        # For statistical analysis, we need to process lines sequentially
        # to build up the statistical baselines
        
        results = []
        
        for line, line_number in lines:
            result = self.detect(line, line_number, file_path)
            if result:
                results.append(result)
        
        return results
    
    def get_statistics_summary(self) -> Dict:
        """Get a summary of collected statistics."""
        return {
            'task_baselines': len(self.baseline_stats),
            'error_types_tracked': len(self.error_frequencies),
            'total_error_instances': sum(self.error_frequencies.values()),
            'tasks_with_duration_data': {
                task: len(durations) 
                for task, durations in self.task_durations.items()
            }
        }
    
    def reset_statistics(self) -> None:
        """Reset all collected statistics."""
        self.task_durations.clear()
        self.task_patterns.clear()
        self.baseline_stats.clear()
        self.error_frequencies.clear()
        self.line_length_stats.clear()
        self.timestamp_intervals.clear()
        print("Statistical baselines reset")
    
    def cleanup(self) -> None:
        """Cleanup method to free memory."""
        self.reset_statistics()
        print("Statistical detector cleaned up") 