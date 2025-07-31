"""
Pattern-based error detector using pyahocorasick for efficient multi-pattern matching.
"""

import re
import ahocorasick
import yaml
from pathlib import Path
from typing import Optional, Dict, List, Set
from functools import lru_cache

from .base import BaseDetector
from ..models.results import DetectionResult


class PatternDetector(BaseDetector):
    """Pattern-based detector using Aho-Corasick algorithm and regex patterns."""
    
    def __init__(self, confidence_threshold: float = 0.7, config_path: Optional[str] = None):
        """
        Initialize the pattern detector.
        
        Args:
            confidence_threshold: Minimum confidence score for detection
            config_path: Path to patterns configuration file
        """
        super().__init__(confidence_threshold)
        self.name = "PatternDetector"
        
        # Load patterns from config
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "patterns.yaml"
        
        self.config = self._load_config(config_path)
        
        # Build Aho-Corasick automaton for exact string matching
        self.automaton = self._build_automaton()
        
        # Compile regex patterns
        self.regex_patterns = self._compile_regex_patterns()
        
        # Pattern weights for confidence calculation
        self.pattern_weights = self.config.get('pattern_weights', {})
        
        # Exclusion patterns to reduce false positives
        self.exclusion_patterns = self._compile_exclusion_patterns()
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            # Fallback to minimal built-in patterns
            print(f"Warning: Could not load config from {config_path}: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration if file loading fails."""
        return {
            'ansible_patterns': {
                'fatal_patterns': ['fatal:', 'FATAL:', 'Fatal:'],
                'failed_patterns': ['failed:', 'FAILED:', 'Failed:', '...failed'],
                'error_patterns': ['error:', 'ERROR:', 'Error:'],
                'unreachable_patterns': ['unreachable:', 'UNREACHABLE:', '...unreachable'],
                'exception_patterns': ['exception:', 'Exception:', 'traceback', 'Traceback'],
                'failure_patterns': ['failure:', 'FAILURE:', '...ignoring']
            },
            'pattern_weights': {
                'fatal_patterns': 0.95,
                'failed_patterns': 0.85,
                'error_patterns': 0.80,
                'unreachable_patterns': 0.90,
                'exception_patterns': 0.85,
                'failure_patterns': 0.75,
                'warning_patterns': 0.75
            }
        }
    
    def _build_automaton(self) -> ahocorasick.Automaton:
        """Build Aho-Corasick automaton for efficient pattern matching."""
        automaton = ahocorasick.Automaton()
        
        # Add all string patterns from config
        pattern_id = 0
        
        for category, patterns in self.config.get('ansible_patterns', {}).items():
            for pattern in patterns:
                automaton.add_word(pattern.lower(), (pattern_id, category, pattern))
                pattern_id += 1
        
        for category, patterns in self.config.get('programming_patterns', {}).items():
            for pattern in patterns:
                # Skip regex patterns for automaton
                if not self._is_regex_pattern(pattern):
                    automaton.add_word(pattern.lower(), (pattern_id, category, pattern))
                    pattern_id += 1
        
        # Add warning patterns that we were missing!
        for pattern in self.config.get('ansible_patterns', {}).get('warning_patterns', []):
            # Skip regex patterns for automaton  
            if not self._is_regex_pattern(pattern):
                automaton.add_word(pattern.lower(), (pattern_id, 'warning_patterns', pattern))
                pattern_id += 1
        
        # Build the automaton
        automaton.make_automaton()
        return automaton
    
    def _is_regex_pattern(self, pattern: str) -> bool:
        """Check if a pattern contains regex metacharacters."""
        regex_chars = set('.*+?^${}[]|()\\')
        return any(char in pattern for char in regex_chars)
    
    def _compile_regex_patterns(self) -> List[tuple]:
        """Compile all regex patterns."""
        compiled_patterns = []
        
        for category, patterns in self.config.get('regex_patterns', {}).items():
            for pattern in patterns:
                try:
                    compiled_regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    compiled_patterns.append((compiled_regex, category, pattern))
                except re.error as e:
                    print(f"Warning: Invalid regex pattern '{pattern}': {e}")
        
        # Add warning regex patterns that were skipped from automaton
        for pattern in self.config.get('ansible_patterns', {}).get('warning_patterns', []):
            if self._is_regex_pattern(pattern):
                try:
                    compiled_regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    compiled_patterns.append((compiled_regex, 'warning_patterns', pattern))
                except re.error as e:
                    print(f"Warning: Invalid warning regex pattern '{pattern}': {e}")
        
        return compiled_patterns
    
    def _compile_exclusion_patterns(self) -> List[re.Pattern]:
        """Compile exclusion patterns to reduce false positives."""
        exclusions = []
        
        # Load all exclusion categories from the new config structure
        exclusion_config = self.config.get('exclusions', {})
        exclusion_categories = [
            'execution_flow',
            'active_operations', 
            'task_metadata',
            'expected_warnings',
            'success_patterns'
        ]
        
        for category in exclusion_categories:
            patterns = exclusion_config.get(category, [])
            for pattern in patterns:
                try:
                    exclusions.append(re.compile(pattern, re.IGNORECASE))
                except re.error as e:
                    print(f"Warning: Invalid exclusion pattern '{pattern}' in {category}: {e}")
        
        return exclusions
    
    def should_detect(self, line: str) -> bool:
        """Quick preprocessing filter to skip obviously irrelevant lines."""
        line_lower = line.lower().strip()
        
        # Skip empty lines
        if not line_lower:
            return False
        
        # Skip comments (basic check)
        if line_lower.startswith('#'):
            return False
        
        # Check for exclusion patterns
        for exclusion in self.exclusion_patterns:
            if exclusion.search(line):
                return False
        
        # Quick check for any error-related keywords (expanded to include warnings)
        error_keywords = ['error', 'fail', 'fatal', 'exception', 'unreachable', 'abort', 
                         'warning', 'deprecated', 'ignoring']
        return any(keyword in line_lower for keyword in error_keywords)
    
    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Detect errors in a single line using pattern matching.
        
        Args:
            line: The log line to analyze
            line_number: Line number in the file (1-indexed)
            file_path: Path to the file being analyzed
            
        Returns:
            DetectionResult if an error is detected, None otherwise
        """
        if not self.should_detect(line):
            return None
        
        confidence = self.get_confidence(line)
        if confidence < self.confidence_threshold:
            return None
        
        error_type = self.get_error_type(line)
        matched_patterns = self.get_matched_patterns(line)
        
        result = DetectionResult(
            file_path=file_path,
            line_number=line_number,
            confidence=confidence,
            error_type=error_type,
            original_line=line.strip(),
            detector_name=self.name,
            matched_patterns=matched_patterns
        )
        
        return result
    
    @lru_cache(maxsize=1000)
    def get_confidence(self, line: str) -> float:
        """
        Calculate confidence score based on pattern matches.
        
        Args:
            line: The log line to analyze
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        line_lower = line.lower()
        max_confidence = 0.0
        
        # Check Aho-Corasick patterns
        for end_index, (pattern_id, category, pattern) in self.automaton.iter(line_lower):
            weight = self.pattern_weights.get(category, 0.7)
            max_confidence = max(max_confidence, weight)
        
        # Check regex patterns
        for regex, category, pattern in self.regex_patterns:
            if regex.search(line):
                weight = self.pattern_weights.get(category, 0.7)
                max_confidence = max(max_confidence, weight)
        
        return max_confidence
    
    @lru_cache(maxsize=1000)
    def get_error_type(self, line: str) -> str:
        """
        Determine the type of error based on matched patterns.
        
        Args:
            line: The log line to analyze
            
        Returns:
            String describing the error type
        """
        line_lower = line.lower()
        matched_categories = []
        
        # Check Aho-Corasick patterns
        for end_index, (pattern_id, category, pattern) in self.automaton.iter(line_lower):
            matched_categories.append(category)
        
        # Check regex patterns
        for regex, category, pattern in self.regex_patterns:
            if regex.search(line):
                matched_categories.append(category)
        
        if not matched_categories:
            return "unknown_error"
        
        # Prioritize error types
        priority_order = [
            'fatal_patterns', 'failed_patterns', 'unreachable_patterns',
            'exception_patterns', 'error_patterns', 'failure_patterns',
            'warning_patterns',  # Added warning patterns to priority order
            'task_status', 'play_recap_errors', 'connection_errors',
            'python_traceback', 'java_stacktrace', 'generic_errors'
        ]
        
        for priority_type in priority_order:
            if priority_type in matched_categories:
                return priority_type.replace('_patterns', '').replace('_', ' ')
        
        return matched_categories[0].replace('_patterns', '').replace('_', ' ')
    
    def get_matched_patterns(self, line: str) -> List[str]:
        """Get all patterns that matched the line."""
        line_lower = line.lower()
        matches = []
        
        # Check Aho-Corasick patterns
        for end_index, (pattern_id, category, pattern) in self.automaton.iter(line_lower):
            matches.append(pattern)
        
        # Check regex patterns
        for regex, category, original_pattern in self.regex_patterns:
            if regex.search(line):
                matches.append(original_pattern)
        
        return matches
    
    def batch_detect(self, lines: List[tuple], file_path: str) -> List[DetectionResult]:
        """
        Optimized batch detection for multiple lines.
        
        Args:
            lines: List of (line_content, line_number) tuples
            file_path: Path to the file being analyzed
            
        Returns:
            List of DetectionResult objects
        """
        # Filter lines that should be processed
        filtered_lines = [(line, line_num) for line, line_num in lines 
                         if self.should_detect(line)]
        
        if not filtered_lines:
            return []
        
        results = []
        for line, line_number in filtered_lines:
            confidence = self.get_confidence(line)
            if confidence >= self.confidence_threshold:
                error_type = self.get_error_type(line)
                matched_patterns = self.get_matched_patterns(line)
                
                result = DetectionResult(
                    file_path=file_path,
                    line_number=line_number,
                    confidence=confidence,
                    error_type=error_type,
                    original_line=line.strip(),
                    detector_name=self.name,
                    matched_patterns=matched_patterns
                )
                results.append(result)
        
        return results
    
    def get_detector_info(self) -> dict:
        """Get information about this detector."""
        total_patterns = 0
        for patterns in self.config.get('ansible_patterns', {}).values():
            total_patterns += len(patterns)
        for patterns in self.config.get('programming_patterns', {}).values():
            total_patterns += len(patterns)
        for patterns in self.config.get('regex_patterns', {}).values():
            total_patterns += len(patterns)
        
        return {
            'name': self.name,
            'confidence_threshold': self.confidence_threshold,
            'type': 'pattern',
            'total_patterns': total_patterns,
            'automaton_size': len(self.automaton),
            'regex_patterns': len(self.regex_patterns)
        } 