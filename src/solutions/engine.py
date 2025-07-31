"""
Hybrid Solution Engine for Ansible log analysis.

This is the main engine that implements ADR-001 Decision #6: Hybrid Troubleshooting Support Strategy.
It combines fast pattern-based solution matching with intelligent LLM fallback for unknown errors.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .pattern_matcher import PatternBasedSolutionMatcher
from .llm_generator import LLMSolutionGenerator

logger = logging.getLogger(__name__)

class HybridSolutionEngine:
    """
    Main hybrid solution engine that combines pattern-based and LLM solution generation.
    
    Architecture Flow (ADR-001):
    Detection Result → Pattern-Based Solutions → LLM Fallback → Actionable Steps
    """
    
    def __init__(self, 
                 config_path: str = "config/patterns.yaml",
                 enable_llm: bool = True,
                 ollama_url: str = "http://localhost:11434",
                 model_name: str = "llama3.1:8b-instruct-q4_0"):
        """
        Initialize the hybrid solution engine.
        
        Args:
            config_path: Path to patterns configuration file
            enable_llm: Whether to enable LLM solution generation
            ollama_url: URL of Ollama server for LLM
            model_name: LLM model name
        """
        self.config_path = config_path
        self.enable_llm = enable_llm
        
        # Initialize pattern-based matcher (always available)
        self.pattern_matcher = PatternBasedSolutionMatcher(config_path)
        
        # Initialize LLM generator (optional)
        self.llm_generator = None
        if enable_llm:
            try:
                self.llm_generator = LLMSolutionGenerator(ollama_url, model_name)
                if not self.llm_generator.is_available:
                    logger.warning("LLM not available - using pattern-only mode")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM generator: {e}")
        
        # Solution engine statistics
        self.stats = {
            'total_requests': 0,
            'pattern_solutions_found': 0,
            'llm_solutions_generated': 0,
            'hybrid_solutions_returned': 0,
            'pattern_only_solutions': 0,
            'llm_only_solutions': 0,
            'no_solutions_found': 0,
            'total_response_time': 0.0
        }
        
        logger.info(f"Hybrid solution engine initialized - LLM: {'enabled' if self.llm_generator and self.llm_generator.is_available else 'disabled'}")
    
    def find_solutions(self, detection_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find solutions using hybrid approach: pattern matching first, LLM fallback.
        
        This implements the core logic of ADR-001 Decision #6.
        
        Args:
            detection_result: Detection result from smart-chunking system
            
        Returns:
            List of solutions with metadata about source and confidence
        """
        start_time = datetime.now()
        self.stats['total_requests'] += 1
        
        error_line = detection_result.get('original_line', '').strip()
        if not error_line:
            logger.debug("Empty error line, skipping solution generation")
            return []
        
        all_solutions = []
        pattern_solutions = []
        llm_solutions = []
        
        # Step 1: Try pattern-based solutions first (fast, validated)
        try:
            pattern_solutions = self.pattern_matcher.find_solutions(detection_result)
            if pattern_solutions:
                self.stats['pattern_solutions_found'] += 1
                all_solutions.extend(pattern_solutions)
                logger.debug(f"Found {len(pattern_solutions)} pattern-based solutions")
        except Exception as e:
            logger.warning(f"Pattern matching failed: {e}")
        
        # Step 2: LLM fallback for unknown/complex errors or to enhance existing solutions  
        if self.llm_generator and self.llm_generator.is_available:
            try:
                # Generate LLM solutions if:
                # - No pattern solutions found, OR
                # - Pattern solutions have low confidence (<0.8), OR
                # - Error has high detection confidence (>0.9) and might benefit from enhanced analysis
                should_use_llm = (
                    len(pattern_solutions) == 0 or
                    (pattern_solutions and max(s.get('confidence', 0) for s in pattern_solutions) < 0.8) or
                    (detection_result.get('confidence', 0) > 0.9 and len(pattern_solutions) < 2)
                )
                
                if should_use_llm:
                    llm_solutions = self.llm_generator.generate_solutions(detection_result)
                    if llm_solutions:
                        self.stats['llm_solutions_generated'] += 1
                        all_solutions.extend(llm_solutions)
                        logger.debug(f"Generated {len(llm_solutions)} LLM solutions")
                        
            except Exception as e:
                logger.warning(f"LLM solution generation failed: {e}")
        
        # Step 3: Merge, deduplicate, and rank solutions
        final_solutions = self._merge_and_rank_solutions(
            pattern_solutions, 
            llm_solutions, 
            detection_result
        )
        
        # Update statistics
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds()
        self.stats['total_response_time'] += response_time
        
        if final_solutions:
            if pattern_solutions and llm_solutions:
                self.stats['hybrid_solutions_returned'] += 1
            elif pattern_solutions:
                self.stats['pattern_only_solutions'] += 1
            elif llm_solutions:
                self.stats['llm_only_solutions'] += 1
        else:
            self.stats['no_solutions_found'] += 1
        
        logger.debug(f"Hybrid engine returned {len(final_solutions)} solutions in {response_time:.3f}s")
        return final_solutions
    
    def _merge_and_rank_solutions(self, 
                                 pattern_solutions: List[Dict[str, Any]], 
                                 llm_solutions: List[Dict[str, Any]],
                                 detection_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Merge, deduplicate, and rank solutions from both sources."""
        
        # Combine all solutions
        all_solutions = []
        
        # Add pattern solutions with source tracking
        for solution in pattern_solutions:
            enhanced = solution.copy()
            enhanced['solution_source'] = 'pattern_database'
            enhanced['hybrid_rank'] = self._calculate_hybrid_rank(enhanced, 'pattern', detection_result)
            all_solutions.append(enhanced)
        
        # Add LLM solutions with source tracking  
        for solution in llm_solutions:
            enhanced = solution.copy()
            enhanced['solution_source'] = 'llm_generated'
            enhanced['hybrid_rank'] = self._calculate_hybrid_rank(enhanced, 'llm', detection_result)
            all_solutions.append(enhanced)
        
        # Remove duplicates based on solution title similarity
        deduplicated = self._deduplicate_solutions(all_solutions)
        
        # Sort by hybrid rank (higher is better)
        ranked_solutions = sorted(deduplicated, key=lambda x: x.get('hybrid_rank', 0), reverse=True)
        
        # Limit to top 3 solutions
        final_solutions = ranked_solutions[:3]
        
        # Add final metadata
        for i, solution in enumerate(final_solutions):
            solution['rank'] = i + 1
            solution['total_solutions_available'] = len(ranked_solutions)
        
        return final_solutions
    
    def _calculate_hybrid_rank(self, solution: Dict[str, Any], source_type: str, 
                              detection_result: Dict[str, Any]) -> float:
        """Calculate hybrid ranking score for solution prioritization."""
        base_confidence = solution.get('confidence', 0.5)
        detection_confidence = detection_result.get('confidence', 0.5)
        
        # Base score from solution confidence
        rank = base_confidence
        
        # Source type adjustments
        if source_type == 'pattern':
            # Pattern solutions get slight boost for reliability
            rank += 0.1
            # Extra boost if pattern matched the exact error
            if solution.get('matched_patterns'):
                rank += 0.05
        elif source_type == 'llm':
            # LLM solutions get boost for high detection confidence (more context available)
            if detection_confidence > 0.8:
                rank += 0.05
        
        # Category-based adjustments
        category = solution.get('category', '')
        high_value_categories = ['ssh_connectivity', 'package_management', 'permissions']
        if category in high_value_categories:
            rank += 0.05
        
        # Time-based preference (favor quicker fixes)
        fix_time = solution.get('estimated_fix_time', '')
        if '5-10 minutes' in fix_time or '5-15 minutes' in fix_time:
            rank += 0.03
        
        # Ensure rank stays in reasonable bounds
        return min(1.0, max(0.0, rank))
    
    def _deduplicate_solutions(self, solutions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate solutions based on title similarity."""
        if len(solutions) <= 1:
            return solutions
        
        unique_solutions = []
        seen_titles = set()
        
        for solution in solutions:
            title = solution.get('title', '').lower().strip()
            
            # Simple deduplication based on key words in title
            title_words = set(title.split())
            
            is_duplicate = False
            for seen_title in seen_titles:
                seen_words = set(seen_title.split())
                # Consider duplicate if >70% word overlap
                overlap = len(title_words & seen_words) / max(len(title_words), len(seen_words))
                if overlap > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_solutions.append(solution)
                seen_titles.add(title)
        
        return unique_solutions
    
    def get_comprehensive_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics from all components."""
        stats = self.stats.copy()
        
        # Add pattern matcher statistics
        if self.pattern_matcher:
            pattern_stats = self.pattern_matcher.get_statistics()
            stats['pattern_matcher'] = pattern_stats
        
        # Add LLM generator statistics
        if self.llm_generator:
            llm_stats = self.llm_generator.get_statistics()
            stats['llm_generator'] = llm_stats
        
        # Calculate derived metrics
        if stats['total_requests'] > 0:
            stats['success_rate'] = (stats['total_requests'] - stats['no_solutions_found']) / stats['total_requests']
            stats['average_response_time'] = stats['total_response_time'] / stats['total_requests']
            stats['pattern_coverage'] = stats['pattern_solutions_found'] / stats['total_requests']
            stats['llm_usage_rate'] = stats['llm_solutions_generated'] / stats['total_requests']
        else:
            stats['success_rate'] = 0.0
            stats['average_response_time'] = 0.0
            stats['pattern_coverage'] = 0.0
            stats['llm_usage_rate'] = 0.0
        
        return stats
    
    def test_hybrid_engine(self, test_cases: List[str]) -> Dict[str, Any]:
        """Test the hybrid engine with multiple test cases."""
        results = []
        
        for i, test_error in enumerate(test_cases):
            test_result = {
                'file_path': f'test_{i}',
                'line_number': 1,
                'confidence': 0.9,
                'error_type': 'test_error',
                'original_line': test_error,
                'context_before': [f'Test context before error {i}'],
                'context_after': [f'Test context after error {i}']
            }
            
            solutions = self.find_solutions(test_result)
            
            results.append({
                'test_case': i + 1,
                'error_line': test_error,
                'solutions_found': len(solutions),
                'solutions': solutions
            })
        
        return {
            'test_results': results,
            'comprehensive_stats': self.get_comprehensive_statistics()
        }
    
    def reload_configuration(self) -> bool:
        """Reload pattern database configuration."""
        try:
            if self.pattern_matcher:
                success = self.pattern_matcher.reload_database()
                if success:
                    logger.info("Hybrid solution engine configuration reloaded")
                return success
            return False
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            return False 