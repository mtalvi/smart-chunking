"""
Abstract base class for all log error detectors.
"""

from abc import ABC, abstractmethod
from typing import List, Iterator, Optional, Tuple
from src.models.results import DetectionResult


class BaseDetector(ABC):
    """Abstract base class for error detectors."""
    
    def __init__(self, confidence_threshold: float = 0.7):
        """
        Initialize the detector.
        
        Args:
            confidence_threshold: Minimum confidence score for detection
        """
        self.confidence_threshold = confidence_threshold
        self.name = self.__class__.__name__
    
    @abstractmethod
    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Detect errors in a single line.
        
        Args:
            line: The log line to analyze
            line_number: Line number in the file (1-indexed)
            file_path: Path to the file being analyzed
            
        Returns:
            DetectionResult if an error is detected, None otherwise
        """
        pass
    
    @abstractmethod
    def get_confidence(self, line: str) -> float:
        """
        Calculate confidence score for a line.
        
        Args:
            line: The log line to analyze
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        pass
    
    @abstractmethod
    def get_error_type(self, line: str) -> str:
        """
        Determine the type of error detected.
        
        Args:
            line: The log line to analyze
            
        Returns:
            String describing the error type
        """
        pass
    
    def batch_detect(self, lines: List[Tuple[str, int]], file_path: str) -> List[DetectionResult]:
        """
        Detect errors in a batch of lines (optional optimization).
        
        Args:
            lines: List of (line_content, line_number) tuples
            file_path: Path to the file being analyzed
            
        Returns:
            List of DetectionResult objects
        """
        results = []
        for line_content, line_number in lines:
            result = self.detect(line_content, line_number, file_path)
            if result:
                results.append(result)
        return results
    
    def should_detect(self, line: str) -> bool:
        """
        Quick check if a line might contain an error (preprocessing filter).
        
        Args:
            line: The log line to check
            
        Returns:
            True if the line should be analyzed further
        """
        # Default implementation - analyze everything
        return True
    
    def setup(self) -> None:
        """Setup method called before processing begins."""
        pass
    
    def cleanup(self) -> None:
        """Cleanup method called after processing completes."""
        pass
    
    def get_detector_info(self) -> dict:
        """Get information about this detector."""
        return {
            'name': self.name,
            'confidence_threshold': self.confidence_threshold,
            'type': 'base'
        } 