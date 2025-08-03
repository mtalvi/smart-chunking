"""
Fixed Semantic error detector that properly excludes timing and execution flow logs.
"""

import numpy as np
import re
from typing import Optional, List, Dict
from functools import lru_cache
import yaml
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available. Semantic detection disabled.")

from src.detectors.base import BaseDetector
from src.models.results import DetectionResult


class SemanticDetector(BaseDetector):
    """Fixed semantic detector that properly excludes timing and operational logs."""
    
    def __init__(self, confidence_threshold: float = 0.75, config_path: Optional[str] = None,
                 model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize the semantic detector.
        
        Args:
            confidence_threshold: Minimum confidence score for detection (raised to 0.75)
            config_path: Path to patterns configuration file
            model_name: Name of the sentence transformer model to use
        """
        super().__init__(confidence_threshold)
        self.name = "SemanticDetector"
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers is required for SemanticDetector")
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "patterns.yaml"
        
        self.config = self._load_config(config_path)
        
        # Initialize the sentence transformer model
        self.model_name = model_name
        self.model = None
        
        # Compile exclusion patterns with enhanced timing patterns
        self.exclusion_patterns = self._compile_exclusion_patterns()
        self.success_patterns = self._compile_success_patterns()
        self.error_embeddings = None
        self.error_phrases = []
        
        # Cache for line embeddings
        self._embedding_cache = {}
        self._cache_max_size = 10000
    
    def setup(self) -> None:
        """Setup method to load model and pre-compute embeddings."""
        if self.model is None:
            print(f"Loading sentence transformer model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            
            # Pre-compute embeddings for error phrases
            self._precompute_error_embeddings()
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration focused on actual errors."""
        return {
            'semantic_phrases': {
                'error_phrases': [
                    # Connection and infrastructure failures
                    "connection could not be established",
                    "ssh connection refused",
                    "host became unreachable", 
                    "timeout waiting for response",
                    "failed to connect to the host via ssh",
                    
                    # Authentication and permission issues
                    "authentication failed",
                    "permission denied",
                    "access denied",
                    "unauthorized access",
                    
                    # File and system errors
                    "file not found",
                    "no such file or directory",
                    "module not found",
                    "command not found",
                    
                    # Configuration and syntax errors
                    "syntax error in playbook",
                    "variable not defined",
                    "configuration validation error",
                    "template rendering failed",
                    
                    # Service and package failures
                    "package installation failed",
                    "service startup failed",
                    "dependency resolution failed",
                    
                    # Critical assertion failures (from real logs)
                    "cluster admin must be created",
                    "assertion evaluation failed",
                    "all assertions failed"
                ]
            }
        }
    
    def _compile_exclusion_patterns(self) -> List[re.Pattern]:
        """Compile exclusion patterns to aggressively filter out timing and operational logs."""
        exclusions = []
        
        # Hardcoded timing patterns that are NEVER errors
        timing_patterns = [
            # Task timing summaries (your main issue)
            r".*---- \d+\.\d+s$",              # "Launch CloudFormation template ---- 158.02s"
            r".*-{10,} \d+\.\d+s$",            # Multiple dashes with timing
            r".* : .* -{4,} \d+\.\d+s$",       # Role-based timing
            r".*\d+\.\d+s \*+$",               # Task timing with asterisks
            r".*===+ \d+\.\d+s$",              # Timing separators
            
            # Task headers and operational flow
            r"^TASK \[.*\] \*+$",              # All task headers
            r"^PLAY \[.*\] \*+$",              # Play headers  
            r"^Run [a-zA-Z]+ [a-zA-Z]+",       # "Run terraform init"
            r"^Wait for .* completion",        # "Wait for ROSA completion"
            r"^Install .*",                    # "Install Helm"
            r"^Create .*",                     # "Create SSH key"
            r"^Save .*",                       # "Save Terraform directory"
            r"^Transfer .*",                   # "Transfer terraform directory"
            r"^Get .*",                        # "Get created subnets"
            r"^Print .*",                      # "Print subnets and OIDC ID"
            
            # Status and informational messages
            r"TASKS RECAP \*+",
            r"===============================================================================",
            r"Friday.*\d{4}.*\+\d{4}.*\*+",   # Timestamp lines
            
            # Successful operations
            r"ok: \[.*\]",
            r"changed: \[.*\]", 
            r"skipping: \[.*\]",
            r"included: .*",
            
            # Retry operations that are still active (not final failures)
            r"FAILED - RETRYING:.*\([2-9]\d* retries left\)",  # Still has retries
            r"FAILED - RETRYING:.*\(1[0-9]+ retries left\)",   # 10+ retries left
            
            # Common non-error patterns
            r"# .*",                           # Comments
            r"debug.*",                        # Debug messages
            r"info.*",                         # Info messages
            r"trace.*",                        # Trace messages
        ]
        
        # Add timing patterns
        for pattern in timing_patterns:
            try:
                exclusions.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                print(f"Warning: Invalid timing exclusion pattern '{pattern}': {e}")
        
        # Load exclusion patterns from config
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
    
    def _compile_success_patterns(self) -> List[re.Pattern]:
        """Compile patterns that indicate successful operations."""
        success_patterns = [
            re.compile(r"successfully", re.IGNORECASE),
            re.compile(r"completed", re.IGNORECASE),
            re.compile(r"finished", re.IGNORECASE),
            re.compile(r"done", re.IGNORECASE),
            re.compile(r"ok:", re.IGNORECASE),
            re.compile(r"passed", re.IGNORECASE),
        ]
        return success_patterns
    
    def should_detect(self, line: str) -> bool:
        """Enhanced preprocessing filter to aggressively exclude non-errors."""
        line_clean = line.strip()
        
        # Skip empty lines
        if not line_clean:
            return False
        
        # Skip very short lines (less than 3 words)
        if len(line_clean.split()) < 3:
            return False
        
        # CRITICAL: Check for exclusion patterns first (your main fix!)
        for exclusion in self.exclusion_patterns:
            if exclusion.search(line_clean):
                return False
        
        # Skip lines that are clearly successful operations
        for success_pattern in self.success_patterns:
            if success_pattern.search(line_clean):
                return False
        
        # Skip lines with timing information (additional safety net)
        if re.search(r'\d+\.\d+s(\s|\*|$)', line_clean):
            return False
        
        # Skip obvious task operation lines
        task_operations = [
            'run ', 'install ', 'create ', 'save ', 'get ', 'transfer ',
            'wait for ', 'print ', 'copy ', 'update ', 'set ', 'check '
        ]
        line_lower = line_clean.lower()
        for op in task_operations:
            if line_lower.startswith(op) and not any(error_word in line_lower 
                                                   for error_word in ['failed', 'error', 'exception', 'denied']):
                return False
        
        # Must contain at least one potential error indicator to proceed (expanded list)
        error_indicators = [
            'fail', 'error', 'exception', 'denied', 'refused', 'timeout',
            'unreachable', 'fatal', 'critical', 'abort', 'panic',
            'warning', 'deprecated', 'unsafe'  # Added to catch warnings
        ]
        
        if not any(indicator in line_lower for indicator in error_indicators):
            return False
        
        return True
    
    def _precompute_error_embeddings(self) -> None:
        """Pre-compute embeddings for error phrases."""
        self.error_phrases = self.config.get('semantic_phrases', {}).get('error_phrases', [])
        
        if not self.error_phrases:
            print("Warning: No error phrases found in configuration")
            self.error_phrases = self._get_default_config()['semantic_phrases']['error_phrases']
        
        print(f"Pre-computing embeddings for {len(self.error_phrases)} error phrases...")
        self.error_embeddings = self.model.encode(self.error_phrases, convert_to_numpy=True)
        print("Embedding pre-computation complete.")
    
    def _get_line_embedding(self, line: str) -> np.ndarray:
        """Get embedding for a line with caching."""
        # Clean the line for consistent caching
        clean_line = line.strip().lower()
        
        if clean_line in self._embedding_cache:
            return self._embedding_cache[clean_line]
        
        # Limit cache size
        if len(self._embedding_cache) >= self._cache_max_size:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(self._embedding_cache.keys())[:self._cache_max_size // 4]
            for key in keys_to_remove:
                del self._embedding_cache[key]
        
        # Compute and cache embedding
        embedding = self.model.encode([clean_line], convert_to_numpy=True)[0]
        self._embedding_cache[clean_line] = embedding
        
        return embedding
    
    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Detect errors using semantic similarity with enhanced filtering.
        """
        if not self.should_detect(line):
            return None
        
        # Ensure model is loaded
        if self.model is None:
            self.setup()
        
        confidence = self.get_confidence(line)
        if confidence < self.confidence_threshold:
            return None
        
        error_type = self.get_error_type(line)
        
        result = DetectionResult(
            file_path=file_path,
            line_number=line_number,
            confidence=confidence,
            error_type=error_type,
            original_line=line.strip(),
            detector_name=self.name
        )
        
        return result
    
    @lru_cache(maxsize=1000)
    def get_confidence(self, line: str) -> float:
        """Calculate confidence score using semantic similarity with stricter thresholds."""
        if self.model is None or self.error_embeddings is None:
            return 0.0
        
        try:
            # Get embedding for the line
            line_embedding = self._get_line_embedding(line)
            
            # Calculate cosine similarities with all error phrases
            similarities = cosine_similarity([line_embedding], self.error_embeddings)[0]
            
            # Get the maximum similarity
            max_similarity = float(np.max(similarities))
            
            # Apply stricter sigmoid transformation to reduce false positives
            # Require higher base similarity (0.6 instead of 0.5)
            confidence = 1 / (1 + np.exp(-12 * (max_similarity - 0.6)))
            
            return min(confidence, 1.0)
            
        except Exception as e:
            print(f"Error computing semantic similarity: {e}")
            return 0.0
    
    @lru_cache(maxsize=1000)
    def get_error_type(self, line: str) -> str:
        """Determine the type of error based on most similar phrase."""
        if self.model is None or self.error_embeddings is None:
            return "semantic_error"
        
        try:
            line_embedding = self._get_line_embedding(line)
            similarities = cosine_similarity([line_embedding], self.error_embeddings)[0]
            
            # Find the most similar error phrase
            best_match_idx = np.argmax(similarities)
            best_phrase = self.error_phrases[best_match_idx]
            
            return self._categorize_error_phrase(best_phrase)
            
        except Exception as e:
            print(f"Error determining semantic error type: {e}")
            return "semantic_error"
    
    def _categorize_error_phrase(self, phrase: str) -> str:
        """Helper method to categorize error phrases."""
        phrase_lower = phrase.lower()
        
        if any(word in phrase_lower for word in ['connection', 'unreachable', 'timeout', 'ssh']):
            return "semantic_connection"
        elif any(word in phrase_lower for word in ['authentication', 'permission', 'denied', 'access']):
            return "semantic_authentication"
        elif any(word in phrase_lower for word in ['file', 'not found', 'directory']):
            return "semantic_file_system"
        elif any(word in phrase_lower for word in ['syntax', 'template', 'variable', 'configuration']):
            return "semantic_configuration"
        elif any(word in phrase_lower for word in ['service', 'package', 'installation', 'dependency']):
            return "semantic_service"
        elif any(word in phrase_lower for word in ['assertion', 'cluster', 'admin']):
            return "semantic_assertion"
        else:
            return "semantic_execution"
    
    def batch_detect(self, lines: List[tuple], file_path: str) -> List[DetectionResult]:
        """Optimized batch detection with better filtering."""
        if self.model is None:
            self.setup()
        
        # Apply stricter filtering
        filtered_lines = [(line, line_num) for line, line_num in lines 
                         if self.should_detect(line)]
        
        if not filtered_lines:
            return []
        
        print(f"Semantic detector: Processing {len(filtered_lines)} lines out of {len(lines)} total")
        
        try:
            # Batch encode all lines at once for efficiency
            line_texts = [line for line, _ in filtered_lines]
            line_embeddings = self.model.encode(line_texts, convert_to_numpy=True)
            
            # Calculate similarities in batch
            similarities_batch = cosine_similarity(line_embeddings, self.error_embeddings)
            
            results = []
            for i, (line, line_number) in enumerate(filtered_lines):
                max_similarity = float(np.max(similarities_batch[i]))
                
                # Apply stricter confidence calculation
                confidence = 1 / (1 + np.exp(-12 * (max_similarity - 0.6)))
                confidence = min(confidence, 1.0)
                
                if confidence >= self.confidence_threshold:
                    # Get error type
                    best_match_idx = np.argmax(similarities_batch[i])
                    best_phrase = self.error_phrases[best_match_idx]
                    error_type = self._categorize_error_phrase(best_phrase)
                    
                    result = DetectionResult(
                        file_path=file_path,
                        line_number=line_number,
                        confidence=confidence,
                        error_type=error_type,
                        original_line=line.strip(),
                        detector_name=self.name
                    )
                    results.append(result)
            
            print(f"Semantic detector: Found {len(results)} potential errors")
            return results
            
        except Exception as e:
            print(f"Error in batch detection: {e}")
            return []
    
    def cleanup(self) -> None:
        """Cleanup method to free memory."""
        if hasattr(self, '_embedding_cache'):
            self._embedding_cache.clear()
    
    def get_detector_info(self) -> dict:
        """Get information about this detector."""
        return {
            'name': self.name,
            'confidence_threshold': self.confidence_threshold,
            'type': 'semantic',
            'model_name': self.model_name,
            'error_phrases_count': len(self.error_phrases) if self.error_phrases else 0,
            'cache_size': len(self._embedding_cache) if hasattr(self, '_embedding_cache') else 0,
            'model_loaded': self.model is not None,
            'exclusion_patterns_count': len(self.exclusion_patterns)
        } 