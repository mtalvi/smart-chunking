"""
Pattern-based solution matcher for Ansible log analysis.

This module implements fast, regex-based solution lookup for known error patterns.
Part of the Hybrid Troubleshooting Support Strategy (ADR-001 Decision #6).
"""

import re
import yaml
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class PatternBasedSolutionMatcher:
    """Fast pattern-based solution matching for known error types."""
    
    def __init__(self, config_path: str = "config/patterns.yaml"):
        """
        Initialize the pattern-based solution matcher.
        
        Args:
            config_path: Path to the patterns configuration file
        """
        self.config_path = Path(config_path)
        self.solutions_db = {}
        self.solution_config = {}
        self.stats = {
            'patterns_loaded': 0,
            'solutions_loaded': 0,
            'matches_found': 0,
            'cache_hits': 0
        }
        self._pattern_cache = {}  # Cache compiled regex patterns
        
        self._load_solution_database()
    
    def _load_solution_database(self) -> None:
        """Load solution database from configuration file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Extract solution database
            self.solutions_db = config.get('ansible_solutions', {})
            self.solution_config = config.get('solution_matching', {
                'use_regex': True,
                'min_confidence': 0.6,
                'max_solutions': 3,
                'sort_by_confidence': True
            })
            
            # Validate and compile patterns
            self._compile_patterns()
            
            logger.info(f"Loaded {self.stats['patterns_loaded']} patterns and {self.stats['solutions_loaded']} solutions")
            
        except FileNotFoundError:
            logger.error(f"Solution database not found: {self.config_path}")
            self.solutions_db = {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing solution database: {e}")
            self.solutions_db = {}
        except Exception as e:
            logger.error(f"Unexpected error loading solution database: {e}")
            self.solutions_db = {}
    
    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for better performance."""
        pattern_count = 0
        solution_count = 0
        
        for solution_category, solution_data in self.solutions_db.items():
            patterns = solution_data.get('patterns', [])
            solutions = solution_data.get('solutions', [])
            
            # Compile patterns if regex is enabled
            if self.solution_config.get('use_regex', True):
                compiled_patterns = []
                for pattern in patterns:
                    try:
                        compiled_pattern = re.compile(pattern, re.IGNORECASE)
                        compiled_patterns.append((pattern, compiled_pattern))
                        pattern_count += 1
                    except re.error as e:
                        logger.warning(f"Invalid regex pattern '{pattern}': {e}")
                        # Fallback to literal string matching
                        compiled_patterns.append((pattern, None))
                        pattern_count += 1
                
                # Cache compiled patterns
                self._pattern_cache[solution_category] = compiled_patterns
            else:
                # Store patterns for literal matching
                self._pattern_cache[solution_category] = [(p, None) for p in patterns]
                pattern_count += len(patterns)
            
            solution_count += len(solutions)
        
        self.stats['patterns_loaded'] = pattern_count  
        self.stats['solutions_loaded'] = solution_count
    
    def find_solutions(self, detection_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find solutions for a detection result using pattern matching.
        
        Args:
            detection_result: Detection result from smart-chunking system
            
        Returns:
            List of matching solutions with confidence scores
        """
        if not self.solutions_db:
            return []
        
        error_line = detection_result.get('original_line', '').strip()
        matched_patterns = detection_result.get('matched_patterns', [])
        error_type = detection_result.get('error_type', '')
        
        if not error_line:
            return []
        
        matching_solutions = []
        
        # Check each solution category
        for solution_category, solution_data in self.solutions_db.items():
            solutions = solution_data.get('solutions', [])
            compiled_patterns = self._pattern_cache.get(solution_category, [])
            
            # Check if any pattern matches
            pattern_matches = self._check_pattern_matches(error_line, compiled_patterns, matched_patterns)
            
            if pattern_matches:
                # Add all solutions from this category
                for solution in solutions:
                    enhanced_solution = self._enhance_solution(
                        solution, 
                        solution_category, 
                        pattern_matches,
                        detection_result
                    )
                    matching_solutions.append(enhanced_solution)
                
                self.stats['matches_found'] += 1
        
        # Filter and sort solutions
        filtered_solutions = self._filter_and_sort_solutions(matching_solutions)
        
        logger.debug(f"Found {len(filtered_solutions)} solutions for error: {error_line[:50]}...")
        return filtered_solutions
    
    def _check_pattern_matches(self, error_line: str, compiled_patterns: List, matched_patterns: List[str]) -> List[str]:
        """Check if error line matches any patterns."""
        matches = []
        
        for pattern_text, compiled_pattern in compiled_patterns:
            match_found = False
            
            if compiled_pattern:
                # Use regex matching
                if compiled_pattern.search(error_line):
                    match_found = True
            else:
                # Use literal string matching
                if pattern_text.lower() in error_line.lower():
                    match_found = True
            
            # Also check against already matched patterns from smart-chunking
            if not match_found:
                for matched_pattern in matched_patterns:
                    if pattern_text.lower() in matched_pattern.lower():
                        match_found = True
                        break
            
            if match_found:
                matches.append(pattern_text)
        
        return matches
    
    def _enhance_solution(self, solution: Dict[str, Any], category: str, 
                         pattern_matches: List[str], detection_result: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance solution with additional metadata."""
        enhanced = solution.copy()
        
        # Add metadata
        enhanced.update({
            'type': 'pattern_match',
            'category': category,
            'matched_patterns': pattern_matches,
            'source': 'pattern_database',
            'confidence_boost': 0.1,  # Boost confidence for pattern matches
            'detection_confidence': detection_result.get('confidence', 0.0)
        })
        
        # Adjust confidence based on detection confidence
        original_confidence = solution.get('confidence', 0.5)
        detection_confidence = detection_result.get('confidence', 0.5)
        
        # Higher detection confidence increases solution confidence
        confidence_multiplier = 0.8 + (detection_confidence * 0.2)
        enhanced['confidence'] = min(0.99, original_confidence * confidence_multiplier)
        
        return enhanced
    
    def _filter_and_sort_solutions(self, solutions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and sort solutions based on configuration."""
        if not solutions:
            return []
        
        # Filter by minimum confidence
        min_confidence = self.solution_config.get('min_confidence', 0.6)
        filtered = [s for s in solutions if s.get('confidence', 0) >= min_confidence]
        
        # Sort by confidence if enabled
        if self.solution_config.get('sort_by_confidence', True):
            filtered.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        # Limit number of solutions
        max_solutions = self.solution_config.get('max_solutions', 3)
        return filtered[:max_solutions]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get matching statistics."""
        return {
            'patterns_loaded': self.stats['patterns_loaded'],
            'solutions_loaded': self.stats['solutions_loaded'],
            'matches_found': self.stats['matches_found'],
            'cache_hits': self.stats['cache_hits'],
            'solution_categories': len(self.solutions_db),
            'database_path': str(self.config_path)
        }
    
    def reload_database(self) -> bool:
        """Reload solution database from configuration file."""
        try:
            self._load_solution_database()
            logger.info("Solution database reloaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to reload solution database: {e}")
            return False
    
    def test_pattern_matching(self, test_error: str) -> Dict[str, Any]:
        """Test pattern matching for a given error string (for debugging)."""
        test_result = {
            'file_path': 'test',
            'line_number': 1,
            'confidence': 0.9,
            'error_type': 'test_error',
            'original_line': test_error,
            'matched_patterns': []
        }
        
        solutions = self.find_solutions(test_result)
        
        return {
            'error_line': test_error,
            'solutions_found': len(solutions),
            'solutions': solutions,
            'statistics': self.get_statistics()
        } 