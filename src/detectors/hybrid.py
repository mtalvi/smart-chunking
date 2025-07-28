"""
Enhanced hybrid detector that combines multiple ML approaches: pattern matching, semantic analysis, 
zero-shot classification, and statistical anomaly detection.
"""

from typing import Optional, List, Dict, Tuple
import numpy as np

from .base import BaseDetector
from .pattern import PatternDetector
from .semantic import SemanticDetector, SENTENCE_TRANSFORMERS_AVAILABLE

try:
    from .zeroshot import ZeroShotErrorClassifier
    ZEROSHOT_AVAILABLE = True
except ImportError:
    ZEROSHOT_AVAILABLE = False

try:
    from .statistical import StatisticalAnomalyDetector
    STATISTICAL_AVAILABLE = True
except ImportError:
    STATISTICAL_AVAILABLE = False

from ..models.results import DetectionResult


class HybridDetector(BaseDetector):
    """Enhanced hybrid detector combining multiple ML approaches for comprehensive error detection."""
    
    def __init__(self, confidence_threshold: float = 0.7, config_path: Optional[str] = None,
                 detector_weights: Optional[Dict[str, float]] = None,
                 enable_zeroshot: bool = True, enable_statistical: bool = True,
                 require_consensus: bool = False, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize the enhanced hybrid detector.
        
        Args:
            confidence_threshold: Minimum confidence score for detection
            config_path: Path to patterns configuration file
            detector_weights: Weights for each detector type {'pattern': 0.3, 'semantic': 0.3, 'zeroshot': 0.2, 'statistical': 0.2}
            enable_zeroshot: Whether to enable zero-shot classification
            enable_statistical: Whether to enable statistical anomaly detection
            require_consensus: If True, multiple detectors must agree for detection
            model_name: Name of the sentence transformer model to use
        """
        super().__init__(confidence_threshold)
        self.name = "HybridDetector"
        
        # Set default weights if not provided
        if detector_weights is None:
            detector_weights = {
                'pattern': 0.4,
                'semantic': 0.3,
                'zeroshot': 0.2,
                'statistical': 0.1
            }
        
        # Normalize weights
        total_weight = sum(detector_weights.values())
        self.detector_weights = {k: v / total_weight for k, v in detector_weights.items()}
        
        self.enable_zeroshot = enable_zeroshot and ZEROSHOT_AVAILABLE
        self.enable_statistical = enable_statistical and STATISTICAL_AVAILABLE
        self.require_consensus = require_consensus
        
        # Initialize sub-detectors with lower individual thresholds
        individual_threshold = 0.4
        
        # Pattern detector (always available)
        self.pattern_detector = PatternDetector(
            confidence_threshold=individual_threshold,
            config_path=config_path
        )
        
        # Semantic detector 
        self.semantic_detector = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.semantic_detector = SemanticDetector(
                    confidence_threshold=individual_threshold,
                    config_path=config_path,
                    model_name=model_name
                )
            except ImportError:
                print("Warning: Could not initialize semantic detector.")
        
        # Zero-shot classifier
        self.zeroshot_detector = None
        if self.enable_zeroshot:
            try:
                self.zeroshot_detector = ZeroShotErrorClassifier(
                    confidence_threshold=individual_threshold
                )
                print("✅ Zero-shot classifier enabled")
            except ImportError:
                print("Warning: Could not initialize zero-shot classifier.")
        
        # Statistical anomaly detector
        self.statistical_detector = None
        if self.enable_statistical:
            try:
                self.statistical_detector = StatisticalAnomalyDetector(
                    confidence_threshold=individual_threshold
                )
                print("✅ Statistical anomaly detector enabled")
            except ImportError:
                print("Warning: Could not initialize statistical detector.")
        
        # Enhanced detection statistics
        self.detection_stats = {
            'pattern_detections': 0,
            'semantic_detections': 0,
            'zeroshot_detections': 0,
            'statistical_detections': 0,
            'consensus_detections': 0,
            'total_detections': 0,
            'detector_combinations': {}
        }
        
        # Active detectors list
        self.active_detectors = self._get_active_detectors()
        print(f"Hybrid detector initialized with {len(self.active_detectors)} active detectors: {list(self.active_detectors.keys())}")
    
    def _get_active_detectors(self) -> Dict[str, BaseDetector]:
        """Get dictionary of active detectors."""
        detectors = {'pattern': self.pattern_detector}
        
        if self.semantic_detector:
            detectors['semantic'] = self.semantic_detector
        if self.zeroshot_detector:
            detectors['zeroshot'] = self.zeroshot_detector
        if self.statistical_detector:
            detectors['statistical'] = self.statistical_detector
        
        return detectors
    
    def setup(self) -> None:
        """Setup method to initialize all active sub-detectors."""
        print("Setting up hybrid detector components...")
        
        self.pattern_detector.setup()
        
        if self.semantic_detector:
            self.semantic_detector.setup()
        
        if self.zeroshot_detector:
            self.zeroshot_detector.setup()
        
        if self.statistical_detector:
            self.statistical_detector.setup()
        
        print(f"✅ Hybrid detector setup complete with {len(self.active_detectors)} active detectors")
    
    def should_detect(self, line: str) -> bool:
        """Quick preprocessing filter using all active detectors."""
        # Use the most permissive filter from any active detector
        for detector in self.active_detectors.values():
            if detector.should_detect(line):
                return True
        
        return False
    
    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Detect errors using enhanced hybrid approach with multiple ML detectors.
        
        Args:
            line: The log line to analyze
            line_number: Line number in the file (1-indexed)
            file_path: Path to the file being analyzed
            
        Returns:
            DetectionResult if an error is detected, None otherwise
        """
        if not self.should_detect(line):
            return None
        
        # Get results from all active detectors
        detector_results = {}
        
        # Pattern detector
        detector_results['pattern'] = self.pattern_detector.detect(line, line_number, file_path)
        
        # Semantic detector
        if self.semantic_detector:
            detector_results['semantic'] = self.semantic_detector.detect(line, line_number, file_path)
        
        # Zero-shot classifier
        if self.zeroshot_detector:
            detector_results['zeroshot'] = self.zeroshot_detector.detect(line, line_number, file_path)
        
        # Statistical anomaly detector
        if self.statistical_detector:
            detector_results['statistical'] = self.statistical_detector.detect(line, line_number, file_path)
        
        # Filter out None results and update statistics
        active_results = {k: v for k, v in detector_results.items() if v is not None}
        
        # Update detection statistics
        for detector_name in detector_results:
            if detector_results[detector_name] is not None:
                self.detection_stats[f'{detector_name}_detections'] += 1
        
        # Record detector combination
        combo_key = '+'.join(sorted(active_results.keys()))
        if combo_key:
            self.detection_stats['detector_combinations'][combo_key] = \
                self.detection_stats['detector_combinations'].get(combo_key, 0) + 1
        
        # Apply consensus logic
        if self.require_consensus:
            # Multiple detectors must agree
            if len(active_results) < 2:
                return None
            self.detection_stats['consensus_detections'] += 1
        else:
            # At least one detector must detect
            if not active_results:
                return None
        
        # Calculate combined confidence, error type, and merge results
        combined_confidence = self._calculate_enhanced_confidence(active_results)
        
        if combined_confidence < self.confidence_threshold:
            return None
        
        combined_error_type = self._determine_enhanced_error_type(active_results)
        combined_patterns, combined_semantic_phrases = self._merge_detection_results(active_results)
        
        # Update total detections
        self.detection_stats['total_detections'] += 1
        
        # Create enhanced hybrid result
        result = DetectionResult(
            file_path=file_path,
            line_number=line_number,
            confidence=combined_confidence,
            error_type=combined_error_type,
            original_line=line.strip(),
            detector_name=self.name,
            matched_patterns=combined_patterns,
            matched_semantic_phrases=combined_semantic_phrases,
            match_details=self._create_enhanced_match_details(active_results)
        )
        
        return result
    
    def _calculate_enhanced_confidence(self, active_results: Dict[str, DetectionResult]) -> float:
        """Calculate combined confidence score from all active detectors."""
        if not active_results:
            return 0.0
        
        if self.require_consensus and len(active_results) >= 2:
            # Use geometric mean for consensus-based scoring (more conservative)
            confidences = [result.confidence for result in active_results.values()]
            return float(np.power(np.prod(confidences), 1.0 / len(confidences)))
        else:
            # Use weighted average based on detector weights
            weighted_sum = 0.0
            total_weight = 0.0
            
            for detector_name, result in active_results.items():
                weight = self.detector_weights.get(detector_name, 0.1)
                weighted_sum += result.confidence * weight
                total_weight += weight
            
            return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _determine_enhanced_error_type(self, active_results: Dict[str, DetectionResult]) -> str:
        """Determine combined error type from all active detectors."""
        if not active_results:
            return "hybrid_unknown"
        
        # Priority order for error type selection
        priority_order = ['pattern', 'statistical', 'semantic', 'zeroshot']
        
        # Find highest priority detector with a result
        for detector_type in priority_order:
            if detector_type in active_results:
                base_type = active_results[detector_type].error_type
                return f"hybrid_{base_type}"
        
        # Fallback to first available result
        first_result = next(iter(active_results.values()))
        return f"hybrid_{first_result.error_type}"
    
    def _merge_detection_results(self, active_results: Dict[str, DetectionResult]) -> Tuple[List[str], List[tuple]]:
        """Merge matched patterns and semantic phrases from all detectors."""
        combined_patterns = []
        combined_semantic_phrases = []
        
        for detector_name, result in active_results.items():
            # Add matched patterns
            if hasattr(result, 'matched_patterns') and result.matched_patterns:
                # Prefix with detector name for clarity
                prefixed_patterns = [f"{detector_name}:{pattern}" for pattern in result.matched_patterns]
                combined_patterns.extend(prefixed_patterns)
            
            # Add semantic phrases
            if hasattr(result, 'matched_semantic_phrases') and result.matched_semantic_phrases:
                # Prefix with detector name for clarity
                prefixed_phrases = [(f"{detector_name}:{phrase}", score) 
                                   for phrase, score in result.matched_semantic_phrases]
                combined_semantic_phrases.extend(prefixed_phrases)
        
        return combined_patterns, combined_semantic_phrases
    
    def _create_enhanced_match_details(self, active_results: Dict[str, DetectionResult]) -> Dict:
        """Create comprehensive match details from all active detectors."""
        match_details = {
            'detection_method': 'hybrid_ml_ensemble',
            'active_detectors': list(active_results.keys()),
            'detector_count': len(active_results),
            'individual_confidences': {},
            'individual_error_types': {},
            'consensus_required': self.require_consensus
        }
        
        # Add individual detector details
        for detector_name, result in active_results.items():
            match_details['individual_confidences'][detector_name] = result.confidence
            match_details['individual_error_types'][detector_name] = result.error_type
            
            # Add detector-specific details if available
            if hasattr(result, 'match_details') and result.match_details:
                match_details[f'{detector_name}_details'] = result.match_details
        
        return match_details
    
    def get_confidence(self, line: str) -> float:
        """Calculate enhanced combined confidence score for a line."""
        confidences = {}
        
        # Get confidence from all active detectors
        confidences['pattern'] = self.pattern_detector.get_confidence(line)
        
        if self.semantic_detector:
            confidences['semantic'] = self.semantic_detector.get_confidence(line)
        
        if self.zeroshot_detector:
            confidences['zeroshot'] = self.zeroshot_detector.get_confidence(line)
        
        if self.statistical_detector:
            confidences['statistical'] = self.statistical_detector.get_confidence(line)
        
        # Filter out zero confidences and calculate weighted average
        active_confidences = {k: v for k, v in confidences.items() if v > 0}
        
        if not active_confidences:
            return 0.0
        
        # Use weighted average
        weighted_sum = 0.0
        total_weight = 0.0
        
        for detector_name, confidence in active_confidences.items():
            weight = self.detector_weights.get(detector_name, 0.1)
            weighted_sum += confidence * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def get_error_type(self, line: str) -> str:
        """Determine enhanced combined error type for a line."""
        error_types = {}
        
        # Get error types from all active detectors
        error_types['pattern'] = self.pattern_detector.get_error_type(line)
        
        if self.semantic_detector:
            error_types['semantic'] = self.semantic_detector.get_error_type(line)
        
        if self.zeroshot_detector:
            error_types['zeroshot'] = self.zeroshot_detector.get_error_type(line)
        
        if self.statistical_detector:
            error_types['statistical'] = self.statistical_detector.get_error_type(line)
        
        # Priority order for error type selection
        priority_order = ['pattern', 'statistical', 'semantic', 'zeroshot']
        
        # Find highest priority detector with a meaningful result
        for detector_type in priority_order:
            if (detector_type in error_types and 
                error_types[detector_type] and 
                error_types[detector_type] != "unknown_error"):
                return f"hybrid_{error_types[detector_type]}"
        
        return "hybrid_unknown_error"
    
    def batch_detect(self, lines: List[Tuple[str, int]], file_path: str) -> List[DetectionResult]:
        """
        Enhanced batch detection combining all active ML detectors.
        
        Args:
            lines: List of (line_content, line_number) tuples
            file_path: Path to the file being analyzed
            
        Returns:
            List of DetectionResult objects
        """
        # Get results from all active detectors
        detector_results = {}
        
        # Pattern detector (always active)
        detector_results['pattern'] = self.pattern_detector.batch_detect(lines, file_path)
        
        # Semantic detector
        if self.semantic_detector:
            detector_results['semantic'] = self.semantic_detector.batch_detect(lines, file_path)
        
        # Zero-shot classifier
        if self.zeroshot_detector:
            detector_results['zeroshot'] = self.zeroshot_detector.batch_detect(lines, file_path)
        
        # Statistical anomaly detector
        if self.statistical_detector:
            detector_results['statistical'] = self.statistical_detector.batch_detect(lines, file_path)
        
        # Create lookup dictionaries for efficient matching
        detector_dicts = {}
        all_detections = set()
        
        for detector_name, results in detector_results.items():
            detector_dicts[detector_name] = {(r.line_number, r.file_path): r for r in results}
            all_detections.update((r.line_number, r.file_path) for r in results)
        
        # Combine results using hybrid logic
        combined_results = []
        
        for line_num, file_path_key in all_detections:
            # Get results from each detector for this line
            line_results = {}
            for detector_name, detector_dict in detector_dicts.items():
                result = detector_dict.get((line_num, file_path_key))
                if result:
                    line_results[detector_name] = result
            
            # Apply consensus logic
            if self.require_consensus and len(line_results) < 2:
                continue
            if not line_results:
                continue
            
            # Calculate combined metrics using the enhanced methods
            combined_confidence = self._calculate_enhanced_confidence(line_results)
            
            if combined_confidence < self.confidence_threshold:
                continue
            
            combined_error_type = self._determine_enhanced_error_type(line_results)
            combined_patterns, combined_semantic_phrases = self._merge_detection_results(line_results)
            
            # Get the original line (from first available result)
            original_line = next(iter(line_results.values())).original_line
            
            # Create enhanced hybrid result
            result = DetectionResult(
                file_path=file_path,
                line_number=line_num,
                confidence=combined_confidence,
                error_type=combined_error_type,
                original_line=original_line,
                detector_name=self.name,
                matched_patterns=combined_patterns,
                matched_semantic_phrases=combined_semantic_phrases,
                match_details=self._create_enhanced_match_details(line_results)
            )
            
            combined_results.append(result)
        
        return combined_results
    
    def get_detailed_analysis(self, line: str) -> Dict:
        """Get detailed analysis from both detectors."""
        analysis = {
            'line': line.strip(),
            'hybrid_confidence': self.get_confidence(line),
            'hybrid_error_type': self.get_error_type(line),
            'pattern_analysis': {
                'confidence': self.pattern_detector.get_confidence(line),
                'error_type': self.pattern_detector.get_error_type(line),
                'matched_patterns': (self.pattern_detector.get_matched_patterns(line)
                                   if hasattr(self.pattern_detector, 'get_matched_patterns') else [])
            },
            'semantic_analysis': None
        }
        
        if self.semantic_detector:
            analysis['semantic_analysis'] = {
                'confidence': self.semantic_detector.get_confidence(line),
                'error_type': self.semantic_detector.get_error_type(line),
                'similar_phrases': (self.semantic_detector.get_most_similar_phrases(line)
                                  if hasattr(self.semantic_detector, 'get_most_similar_phrases') else [])
            }
        
        return analysis
    
    def cleanup(self) -> None:
        """Cleanup method for both detectors."""
        self.pattern_detector.cleanup()
        if self.semantic_detector:
            self.semantic_detector.cleanup()
    
    def get_detector_info(self) -> dict:
        """Get information about this detector."""
        info = {
            'name': self.name,
            'confidence_threshold': self.confidence_threshold,
            'type': 'hybrid',
            'pattern_weight': self.pattern_weight,
            'semantic_weight': self.semantic_weight,
            'require_both': self.require_both,
            'detection_stats': self.detection_stats,
            'pattern_detector': self.pattern_detector.get_detector_info(),
            'semantic_detector': (self.semantic_detector.get_detector_info()
                                if self.semantic_detector else None)
        }
        
        return info
    
    def get_detection_statistics(self) -> Dict:
        """Get detection statistics."""
        total = self.detection_stats['total_detections']
        if total == 0:
            return self.detection_stats
        
        stats = self.detection_stats.copy()
        stats['percentages'] = {
            'pattern_only': (self.detection_stats['pattern_only'] / total) * 100,
            'semantic_only': (self.detection_stats['semantic_only'] / total) * 100,
            'both_detected': (self.detection_stats['both_detected'] / total) * 100
        }
        
        return stats 