"""
Solutions package for the Ansible Log Monitoring System.

This package implements the Hybrid Troubleshooting Support Strategy from ADR-001 Decision #6.
It provides pattern-based solution matching with LLM fallback for unknown errors.
"""

from .engine import HybridSolutionEngine
from .pattern_matcher import PatternBasedSolutionMatcher
from .llm_generator import LLMSolutionGenerator

__all__ = [
    'HybridSolutionEngine',
    'PatternBasedSolutionMatcher', 
    'LLMSolutionGenerator'
]

__version__ = '0.1.0'
