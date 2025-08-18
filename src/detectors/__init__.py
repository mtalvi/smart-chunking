"""
Detectors package - Contains various detection strategies for log analysis.
"""

from src.detectors.base import BaseDetector
from src.detectors.pattern import PatternDetector

# Optional semantic, hybrid, and contextual detectors
try:
    from src.detectors.semantic import SemanticDetector
    from src.detectors.hybrid import HybridDetector
    from src.detectors.contextual import ContextualCorrelationDetector
    __all__ = ['BaseDetector', 'PatternDetector', 'SemanticDetector', 'HybridDetector', 'ContextualCorrelationDetector']
except ImportError as e:
    print(f"Warning: Advanced analysis not available: {e}")
    __all__ = ['BaseDetector', 'PatternDetector'] 