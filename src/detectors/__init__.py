"""
Detectors package - Contains various detection strategies for log analysis.
"""

from .base import BaseDetector
from .pattern import PatternDetector

# Optional semantic and hybrid detectors
try:
    from .semantic import SemanticDetector
    from .hybrid import HybridDetector
    __all__ = ['BaseDetector', 'PatternDetector', 'SemanticDetector', 'HybridDetector']
except ImportError as e:
    print(f"Warning: Semantic analysis not available: {e}")
    __all__ = ['BaseDetector', 'PatternDetector'] 