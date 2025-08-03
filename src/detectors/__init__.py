"""
Detectors package - Contains various detection strategies for log analysis.
"""

from src.detectors.base import BaseDetector
from src.detectors.pattern import PatternDetector

# Optional semantic and hybrid detectors
try:
    from src.detectors.semantic import SemanticDetector
    from src.detectors.hybrid import HybridDetector
    __all__ = ['BaseDetector', 'PatternDetector', 'SemanticDetector', 'HybridDetector']
except ImportError as e:
    print(f"Warning: Semantic analysis not available: {e}")
    __all__ = ['BaseDetector', 'PatternDetector'] 