"""
Error clustering processor for grouping similar errors using machine learning.
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import numpy as np

try:
    from sklearn.cluster import DBSCAN
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Warning: scikit-learn not available. Error clustering disabled.")

from ..models.results import DetectionResult, AnalysisResults


class ErrorClusterer:
    """Cluster similar errors together using unsupervised machine learning."""
    
    def __init__(self, eps: float = 0.3, min_samples: int = 2, 
                 max_features: int = 1000, ngram_range: Tuple[int, int] = (1, 3)):
        """
        Initialize the error clusterer.
        
        Args:
            eps: DBSCAN epsilon parameter - maximum distance between samples
            min_samples: DBSCAN min_samples parameter - minimum samples in neighborhood  
            max_features: Maximum number of TF-IDF features
            ngram_range: N-gram range for TF-IDF vectorization
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn is required for ErrorClusterer")
        
        self.eps = eps
        self.min_samples = min_samples
        self.max_features = max_features
        self.ngram_range = ngram_range
        
        # Initialize components
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            stop_words='english',
            ngram_range=ngram_range,
            lowercase=True,
            token_pattern=r'\b\w+\b'  # Simple word tokenization
        )
        
        self.clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        
        # Clustering results
        self.cluster_labels = None
        self.cluster_summaries = {}
        self.error_vectors = None
        
    def cluster_errors(self, results: List[DetectionResult]) -> Dict[int, Dict]:
        """
        Group similar errors together using clustering.
        
        Args:
            results: List of DetectionResult objects to cluster
            
        Returns:
            Dictionary mapping cluster_id to cluster information
        """
        if not results:
            return {}
        
        print(f"Clustering {len(results)} errors...")
        
        # Extract error messages for clustering
        error_messages = [result.original_line for result in results]
        
        try:
            # Transform errors to TF-IDF vectors
            print("Vectorizing error messages...")
            self.error_vectors = self.vectorizer.fit_transform(error_messages)
            
            # Perform clustering
            print("Performing DBSCAN clustering...")
            self.cluster_labels = self.clusterer.fit_predict(self.error_vectors)
            
            # Group errors by cluster
            clustered_errors = self._group_by_cluster(results, self.cluster_labels)
            
            # Generate cluster summaries
            self.cluster_summaries = self._generate_cluster_summaries(clustered_errors)
            
            print(f"Found {len([c for c in self.cluster_labels if c != -1])} clusters")
            print(f"Noise points (unclustered): {len([c for c in self.cluster_labels if c == -1])}")
            
            return self.cluster_summaries
            
        except Exception as e:
            print(f"Error during clustering: {e}")
            return {}
    
    def _group_by_cluster(self, results: List[DetectionResult], 
                         cluster_labels: np.ndarray) -> Dict[int, List[DetectionResult]]:
        """Group results by their cluster labels."""
        clustered_errors = defaultdict(list)
        
        for idx, cluster_id in enumerate(cluster_labels):
            clustered_errors[cluster_id].append(results[idx])
        
        return clustered_errors
    
    def _generate_cluster_summaries(self, clustered_errors: Dict[int, List[DetectionResult]]) -> Dict[int, Dict]:
        """Generate summaries for each cluster."""
        cluster_summaries = {}
        
        for cluster_id, errors in clustered_errors.items():
            if cluster_id == -1:  # Noise cluster in DBSCAN
                cluster_summaries[cluster_id] = {
                    'representative_error': None,
                    'count': len(errors),
                    'all_errors': errors,
                    'cluster_type': 'noise',
                    'description': f"Unclustered errors ({len(errors)} unique issues)",
                    'error_types': list(set(error.error_type for error in errors)),
                    'files_affected': list(set(error.file_path for error in errors)),
                    'confidence_range': {
                        'min': min(error.confidence for error in errors),
                        'max': max(error.confidence for error in errors),
                        'avg': sum(error.confidence for error in errors) / len(errors)
                    }
                }
            else:
                # Find representative error (closest to cluster centroid)
                representative = self._find_representative_error(cluster_id, errors)
                
                # Generate descriptive summary
                description = self._generate_cluster_description(errors)
                
                cluster_summaries[cluster_id] = {
                    'representative_error': representative,
                    'count': len(errors),
                    'all_errors': errors,
                    'cluster_type': 'similar_errors',
                    'description': description,
                    'error_types': list(set(error.error_type for error in errors)),
                    'files_affected': list(set(error.file_path for error in errors)),
                    'confidence_range': {
                        'min': min(error.confidence for error in errors),
                        'max': max(error.confidence for error in errors),
                        'avg': sum(error.confidence for error in errors) / len(errors)
                    },
                    'line_numbers': [error.line_number for error in errors],
                    'detector_sources': list(set(error.detector_name for error in errors))
                }
        
        return cluster_summaries
    
    def _find_representative_error(self, cluster_id: int, errors: List[DetectionResult]) -> DetectionResult:
        """Find the error that best represents the cluster."""
        if len(errors) == 1:
            return errors[0]
        
        try:
            # Get indices of errors in this cluster
            cluster_indices = [i for i, label in enumerate(self.cluster_labels) if label == cluster_id]
            
            # Get vectors for this cluster - convert to dense array to avoid matrix issues  
            cluster_vectors = self.error_vectors[cluster_indices]
            if hasattr(cluster_vectors, 'todense'):
                cluster_vectors = cluster_vectors.todense()
            cluster_vectors = np.asarray(cluster_vectors)
            
            # Calculate centroid - ensure it's a numpy array
            centroid = np.asarray(cluster_vectors.mean(axis=0))
            if centroid.ndim > 1:
                centroid = centroid.flatten()
            
            # Reshape centroid for cosine_similarity
            centroid = centroid.reshape(1, -1)
            
            # Find error closest to centroid
            similarities = cosine_similarity(centroid, cluster_vectors)[0]
            representative_idx = np.argmax(similarities)
            
            return errors[representative_idx]
            
        except Exception as e:
            print(f"Error finding representative for cluster {cluster_id}: {e}")
            # Fallback: return the error with highest confidence
            return max(errors, key=lambda x: x.confidence)
    
    def _generate_cluster_description(self, errors: List[DetectionResult]) -> str:
        """Generate a human-readable description of the cluster."""
        if len(errors) == 1:
            return f"Single error: {errors[0].error_type}"
        
        # Analyze common patterns
        error_types = [error.error_type for error in errors]
        most_common_type = max(set(error_types), key=error_types.count)
        
        files = list(set(error.file_path for error in errors))
        file_count = len(files)
        
        # Extract common keywords from error messages
        common_keywords = self._extract_common_keywords([error.original_line for error in errors])
        
        # Generate description
        if file_count == 1:
            file_desc = f"in {files[0]}"
        elif file_count <= 3:
            file_desc = f"across {file_count} files"
        else:
            file_desc = f"across {file_count} files"
        
        keyword_desc = f" involving {', '.join(common_keywords[:3])}" if common_keywords else ""
        
        return f"{len(errors)} similar {most_common_type} errors {file_desc}{keyword_desc}"
    
    def _extract_common_keywords(self, messages: List[str], min_frequency: int = 2) -> List[str]:
        """Extract keywords that appear frequently across messages."""
        try:
            # Use a simple approach to find common meaningful words
            from collections import Counter
            import re
            
            # Extract words (excluding very common/short words)
            words = []
            stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had'}
            
            for message in messages:
                # Extract meaningful words (alphanumeric, length > 3)
                message_words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]*\b', message.lower())
                words.extend([word for word in message_words 
                            if len(word) > 3 and word not in stop_words])
            
            # Find words that appear in multiple messages
            word_counts = Counter(words)
            common_words = [word for word, count in word_counts.items() 
                          if count >= min_frequency and count >= len(messages) * 0.3]
            
            # Sort by frequency and return top keywords
            return sorted(common_words, key=word_counts.get, reverse=True)
            
        except Exception as e:
            print(f"Error extracting keywords: {e}")
            return []
    
    def apply_clustering_to_results(self, analysis_results: AnalysisResults) -> AnalysisResults:
        """
        Apply clustering to an AnalysisResults object and update it with clustering information.
        
        Args:
            analysis_results: AnalysisResults object to process
            
        Returns:
            Updated AnalysisResults object with clustering information
        """
        if not analysis_results.results:
            return analysis_results
        
        # Perform clustering
        cluster_summaries = self.cluster_errors(analysis_results.results)
        
        # Update results with cluster information
        updated_results = []
        
        for idx, result in enumerate(analysis_results.results):
            cluster_id = self.cluster_labels[idx] if self.cluster_labels is not None else -1
            
            # Add cluster information to match_details
            if not hasattr(result, 'match_details') or result.match_details is None:
                result.match_details = {}
            
            result.match_details.update({
                'cluster_id': int(cluster_id),
                'cluster_size': cluster_summaries.get(cluster_id, {}).get('count', 1),
                'is_representative': (result == cluster_summaries.get(cluster_id, {}).get('representative_error', None)),
                'cluster_description': cluster_summaries.get(cluster_id, {}).get('description', 'Single error')
            })
            
            updated_results.append(result)
        
        # Update the analysis results
        analysis_results.results = updated_results
        
        # Add clustering metadata
        if not hasattr(analysis_results, 'metadata'):
            analysis_results.metadata = {}
        
        analysis_results.metadata.update({
            'clustering_applied': True,
            'total_clusters': len([c for c in cluster_summaries.keys() if c != -1]),
            'noise_points': cluster_summaries.get(-1, {}).get('count', 0),
            'clustering_parameters': {
                'eps': self.eps,
                'min_samples': self.min_samples,
                'max_features': self.max_features,
                'ngram_range': self.ngram_range
            }
        })
        
        print(f"✅ Applied clustering: {len([c for c in cluster_summaries.keys() if c != -1])} clusters found")
        
        return analysis_results
    
    def get_cluster_summary(self, cluster_id: int) -> Optional[Dict]:
        """Get summary information for a specific cluster."""
        return self.cluster_summaries.get(cluster_id)
    
    def get_similar_errors(self, error_text: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Find errors similar to the given error text.
        
        Args:
            error_text: Error text to find similarities for
            top_k: Number of top similar errors to return
            
        Returns:
            List of (similar_error_text, similarity_score) tuples
        """
        if self.error_vectors is None:
            return []
        
        try:
            # Transform the query error text
            query_vector = self.vectorizer.transform([error_text])
            
            # Calculate similarities
            similarities = cosine_similarity(query_vector, self.error_vectors)[0]
            
            # Get top-k most similar
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            # Get original error texts (this would need to be stored)
            # For now, return indices and similarities
            results = []
            for idx in top_indices:
                similarity = float(similarities[idx])
                if similarity > 0.1:  # Minimum similarity threshold
                    results.append((f"Error_{idx}", similarity))
            
            return results
            
        except Exception as e:
            print(f"Error finding similar errors: {e}")
            return []
    
    def get_clustering_statistics(self) -> Dict:
        """Get statistics about the clustering results."""
        if self.cluster_labels is None:
            return {'status': 'no_clustering_performed'}
        
        cluster_counts = defaultdict(int)
        for label in self.cluster_labels:
            cluster_counts[label] += 1
        
        # Remove noise cluster (-1) for statistics
        actual_clusters = {k: v for k, v in cluster_counts.items() if k != -1}
        
        stats = {
            'total_clusters': len(actual_clusters),
            'noise_points': cluster_counts.get(-1, 0),
            'total_points': len(self.cluster_labels),
            'cluster_sizes': dict(actual_clusters),
            'avg_cluster_size': np.mean(list(actual_clusters.values())) if actual_clusters else 0,
            'largest_cluster_size': max(actual_clusters.values()) if actual_clusters else 0,
            'smallest_cluster_size': min(actual_clusters.values()) if actual_clusters else 0,
            'clustering_parameters': {
                'eps': self.eps,
                'min_samples': self.min_samples,
                'max_features': self.max_features,
                'ngram_range': self.ngram_range
            }
        }
        
        return stats
    
    def export_clusters_to_dict(self) -> Dict:
        """Export cluster summaries to a dictionary for JSON serialization."""
        if not self.cluster_summaries:
            return {}
        
        exportable_clusters = {}
        
        for cluster_id, summary in self.cluster_summaries.items():
            exportable_clusters[str(cluster_id)] = {
                'cluster_id': cluster_id,
                'count': summary['count'],
                'cluster_type': summary['cluster_type'],
                'description': summary['description'],
                'error_types': summary['error_types'],
                'files_affected': summary['files_affected'],
                'confidence_range': summary['confidence_range'],
                'representative_error': {
                    'file_path': summary['representative_error'].file_path,
                    'line_number': summary['representative_error'].line_number,
                    'original_line': summary['representative_error'].original_line,
                    'error_type': summary['representative_error'].error_type,
                    'confidence': summary['representative_error'].confidence
                } if summary['representative_error'] else None,
                'line_numbers': summary.get('line_numbers', []),
                'detector_sources': summary.get('detector_sources', [])
            }
        
        return exportable_clusters
    
    def cleanup(self) -> None:
        """Cleanup method to free memory."""
        self.cluster_labels = None
        self.cluster_summaries.clear()
        self.error_vectors = None
        print("Error clusterer cleaned up") 