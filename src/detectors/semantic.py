"""
Semantic error detector using sentence transformers for context-aware analysis.
"""

import numpy as np
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

from .base import BaseDetector
from ..models.results import DetectionResult


class SemanticDetector(BaseDetector):
    """Semantic detector using sentence transformers for NLP-based error detection."""
    
    def __init__(self, confidence_threshold: float = 0.7, config_path: Optional[str] = None,
                 model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize the semantic detector.
        
        Args:
            confidence_threshold: Minimum confidence score for detection
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
        """Get default configuration if file loading fails."""
        return {
            'semantic_phrases': {
                'error_phrases': [
                    "task execution failed",
                    "playbook execution error",
                    "connection could not be established",
                    "authentication failed",
                    "permission denied",
                    "file not found",
                    "module not found",
                    "syntax error in playbook",
                    "variable not defined",
                    "template rendering failed",
                    "host became unreachable",
                    "timeout waiting for response",
                    "certificate verification failed",
                    "package installation failed",
                    "service startup failed",
                    "configuration validation error"
                ]
            }
        }
    
    def _precompute_error_embeddings(self) -> None:
        """Pre-compute embeddings for error phrases."""
        self.error_phrases = self.config.get('semantic_phrases', {}).get('error_phrases', [])
        
        if not self.error_phrases:
            print("Warning: No error phrases found in configuration")
            return
        
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
    
    def should_detect(self, line: str) -> bool:
        """Quick preprocessing filter."""
        line_clean = line.strip().lower()
        
        # Skip empty lines
        if not line_clean:
            return False
        
        # Skip very short lines (less than 3 words)
        if len(line_clean.split()) < 3:
            return False
        
        # Skip obvious non-error lines
        skip_patterns = ['info:', 'debug:', 'trace:', '# ', 'changed:', 'ok:']
        for pattern in skip_patterns:
            if line_clean.startswith(pattern):
                return False
        
        return True
    
    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Detect errors using semantic similarity.
        
        Args:
            line: The log line to analyze
            line_number: Line number in the file (1-indexed)
            file_path: Path to the file being analyzed
            
        Returns:
            DetectionResult if an error is detected, None otherwise
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
        """
        Calculate confidence score using semantic similarity.
        
        Args:
            line: The log line to analyze
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if self.model is None or self.error_embeddings is None:
            return 0.0
        
        try:
            # Get embedding for the line
            line_embedding = self._get_line_embedding(line)
            
            # Calculate cosine similarities with all error phrases
            similarities = cosine_similarity([line_embedding], self.error_embeddings)[0]
            
            # Return the maximum similarity as confidence
            max_similarity = float(np.max(similarities))
            
            # Apply a sigmoid-like transformation to make the threshold more meaningful
            # This helps distinguish between similar and very similar phrases
            confidence = 1 / (1 + np.exp(-10 * (max_similarity - 0.5)))
            
            return min(confidence, 1.0)
            
        except Exception as e:
            print(f"Error computing semantic similarity: {e}")
            return 0.0
    
    @lru_cache(maxsize=1000)
    def get_error_type(self, line: str) -> str:
        """
        Determine the type of error based on most similar phrase.
        
        Args:
            line: The log line to analyze
            
        Returns:
            String describing the error type
        """
        if self.model is None or self.error_embeddings is None:
            return "semantic_error"
        
        try:
            # Get embedding for the line
            line_embedding = self._get_line_embedding(line)
            
            # Calculate cosine similarities
            similarities = cosine_similarity([line_embedding], self.error_embeddings)[0]
            
            # Find the most similar error phrase
            best_match_idx = np.argmax(similarities)
            best_phrase = self.error_phrases[best_match_idx]
            
            # Map phrase to error type category
            error_type_mapping = {
                'connection': ['connection', 'unreachable', 'timeout', 'ssh'],
                'authentication': ['authentication', 'permission', 'denied'],
                'file_system': ['file not found', 'permission denied'],
                'execution': ['execution', 'failed', 'error'],
                'configuration': ['configuration', 'validation', 'syntax'],
                'service': ['service', 'startup', 'package'],
                'template': ['template', 'rendering', 'variable']
            }
            
            # Categorize based on keywords in the best matching phrase
            best_phrase_lower = best_phrase.lower()
            for category, keywords in error_type_mapping.items():
                if any(keyword in best_phrase_lower for keyword in keywords):
                    return f"semantic_{category}"
            
            return "semantic_error"
            
        except Exception as e:
            print(f"Error determining semantic error type: {e}")
            return "semantic_error"
    
    def get_most_similar_phrases(self, line: str, top_k: int = 3) -> List[tuple]:
        """
        Get the most similar error phrases for a line.
        
        Args:
            line: The log line to analyze
            top_k: Number of top similar phrases to return
            
        Returns:
            List of (phrase, similarity_score) tuples
        """
        if self.model is None or self.error_embeddings is None:
            return []
        
        try:
            line_embedding = self._get_line_embedding(line)
            similarities = cosine_similarity([line_embedding], self.error_embeddings)[0]
            
            # Get top-k most similar phrases
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                phrase = self.error_phrases[idx]
                similarity = float(similarities[idx])
                results.append((phrase, similarity))
            
            return results
            
        except Exception as e:
            print(f"Error getting similar phrases: {e}")
            return []
    
    def batch_detect(self, lines: List[tuple], file_path: str) -> List[DetectionResult]:
        """
        Optimized batch detection for multiple lines.
        
        Args:
            lines: List of (line_content, line_number) tuples
            file_path: Path to the file being analyzed
            
        Returns:
            List of DetectionResult objects
        """
        if self.model is None:
            self.setup()
        
        # Filter lines that should be processed
        filtered_lines = [(line, line_num) for line, line_num in lines 
                         if self.should_detect(line)]
        
        if not filtered_lines:
            return []
        
        try:
            # Batch encode all lines at once for efficiency
            line_texts = [line for line, _ in filtered_lines]
            line_embeddings = self.model.encode(line_texts, convert_to_numpy=True)
            
            # Calculate similarities in batch
            similarities_batch = cosine_similarity(line_embeddings, self.error_embeddings)
            
            results = []
            for i, (line, line_number) in enumerate(filtered_lines):
                max_similarity = float(np.max(similarities_batch[i]))
                confidence = 1 / (1 + np.exp(-10 * (max_similarity - 0.5)))
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
            
            return results
            
        except Exception as e:
            print(f"Error in batch detection: {e}")
            # Fallback to individual detection
            return super().batch_detect(filtered_lines, file_path)
    
    def _categorize_error_phrase(self, phrase: str) -> str:
        """Helper method to categorize error phrases."""
        phrase_lower = phrase.lower()
        
        if any(word in phrase_lower for word in ['connection', 'unreachable', 'timeout', 'ssh']):
            return "semantic_connection"
        elif any(word in phrase_lower for word in ['authentication', 'permission', 'denied']):
            return "semantic_authentication"
        elif any(word in phrase_lower for word in ['file', 'not found']):
            return "semantic_file_system"
        elif any(word in phrase_lower for word in ['execution', 'failed', 'error']):
            return "semantic_execution"
        elif any(word in phrase_lower for word in ['configuration', 'validation', 'syntax']):
            return "semantic_configuration"
        elif any(word in phrase_lower for word in ['service', 'startup', 'package']):
            return "semantic_service"
        elif any(word in phrase_lower for word in ['template', 'rendering', 'variable']):
            return "semantic_template"
        else:
            return "semantic_error"
    
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
            'model_loaded': self.model is not None
        } 