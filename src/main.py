"""
Main CLI application for the Log Error Extractor.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from .detectors import PatternDetector, SemanticDetector, HybridDetector
from .processors import StreamProcessor, ContextExtractor
from .models.results import AnalysisResults

# Import new ML detectors with fallback handling
try:
    from .detectors.zeroshot import ZeroShotErrorClassifier
    ZEROSHOT_AVAILABLE = True
except ImportError:
    ZEROSHOT_AVAILABLE = False

try:
    from .detectors.statistical import StatisticalAnomalyDetector
    STATISTICAL_AVAILABLE = True
except ImportError:
    STATISTICAL_AVAILABLE = False

try:
    from .processors.clusterer import ErrorClusterer
    CLUSTERING_AVAILABLE = True
except ImportError:
    CLUSTERING_AVAILABLE = False


def setup_spacy_gpu():
    """Setup spaCy to use GPU if available."""
    try:
        import spacy
        if spacy.prefer_gpu():
            logger.info("GPU acceleration enabled for spaCy")
        else:
            logger.info("GPU not available, using CPU")
    except ImportError:
        logger.warning("spaCy not available")
    except Exception as e:
        logger.warning(f"Could not setup spaCy GPU: {e}")


def create_detector(detector_type: str, confidence_threshold: float, config_path: Optional[str] = None, 
                   enable_clustering: bool = False, **kwargs):
    """
    Create a detector instance based on the specified type.
    
    Args:
        detector_type: Type of detector ('pattern', 'semantic', 'hybrid', 'zeroshot', 'statistical')
        confidence_threshold: Minimum confidence threshold
        config_path: Optional path to configuration file
        enable_clustering: Whether to enable error clustering
        **kwargs: Additional arguments for specific detectors
        
    Returns:
        Detector instance
    """
    detector = None
    
    if detector_type == 'pattern':
        detector = PatternDetector(
            confidence_threshold=confidence_threshold,
            config_path=config_path
        )
    elif detector_type == 'semantic':
        try:
            detector = SemanticDetector(
                confidence_threshold=confidence_threshold,
                config_path=config_path
            )
        except ImportError as e:
            logger.error("Semantic detector requires sentence-transformers. Install with: pip install sentence-transformers")
            sys.exit(1)
    elif detector_type == 'zeroshot':
        if not ZEROSHOT_AVAILABLE:
            logger.error("Zero-shot classifier requires transformers. Install with: pip install transformers")
            sys.exit(1)
        try:
            detector = ZeroShotErrorClassifier(
                confidence_threshold=confidence_threshold
            )
        except Exception as e:
            logger.error(f"Failed to initialize zero-shot classifier: {e}")
            sys.exit(1)
    elif detector_type == 'statistical':
        if not STATISTICAL_AVAILABLE:
            logger.error("Statistical detector requires numpy and scipy. Install with: pip install numpy scipy")
            sys.exit(1)
        try:
            detector = StatisticalAnomalyDetector(
                confidence_threshold=confidence_threshold,
                z_threshold=kwargs.get('z_threshold', 3.0),
                min_samples=kwargs.get('min_samples', 5)
            )
        except Exception as e:
            logger.error(f"Failed to initialize statistical detector: {e}")
            sys.exit(1)
    elif detector_type == 'hybrid':
        try:
            # Enhanced hybrid detector with new ML capabilities
            detector = HybridDetector(
                confidence_threshold=confidence_threshold,
                config_path=config_path,
                enable_zeroshot=kwargs.get('enable_zeroshot', True),
                enable_statistical=kwargs.get('enable_statistical', True),
                require_consensus=kwargs.get('require_consensus', False)
            )
        except ImportError as e:
            logger.warning("Hybrid detector falling back to pattern-only mode due to missing dependencies")
            detector = PatternDetector(
                confidence_threshold=confidence_threshold,
                config_path=config_path
            )
    else:
        raise ValueError(f"Unknown detector type: {detector_type}. "
                        f"Available types: pattern, semantic, zeroshot, statistical, hybrid")
    
    return detector


def save_results(results: AnalysisResults, output_path: str, output_format: str):
    """
    Save analysis results to the specified format.
    
    Args:
        results: AnalysisResults object to save
        output_path: Path to save the results
        output_format: Format to save ('json', 'csv', 'msgpack')
    """
    output_file = Path(output_path)
    
    try:
        if output_format == 'json':
            results.to_json(output_file)
        elif output_format == 'csv':
            results.to_csv(output_file)
        elif output_format == 'msgpack':
            results.to_msgpack(output_file)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
        
        logger.info(f"Results saved to {output_path}")
        
    except Exception as e:
        logger.error(f"Error saving results: {e}")
        sys.exit(1)


def print_summary(results: AnalysisResults):
    """Print a summary of the analysis results."""
    summary = results.get_summary()
    
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    
    print(f"Total errors found: {summary['total_errors']}")
    print(f"Files with errors: {summary['files_with_errors']}")
    print(f"Average confidence: {summary['avg_confidence']:.2f}")
    
    print(f"\nProcessing Statistics:")
    stats = summary['processing_stats']
    print(f"  Files processed: {stats['total_files_processed']}")
    print(f"  Lines processed: {stats['total_lines_processed']}")
    print(f"  Processing time: {stats['processing_time']:.2f} seconds")
    
    if summary['error_types']:
        print(f"\nError Types:")
        for error_type, count in sorted(summary['error_types'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {error_type}: {count}")
    
    if summary['detector_stats']:
        print(f"\nDetector Statistics:")
        for detector, count in summary['detector_stats'].items():
            print(f"  {detector}: {count}")


def print_detailed_results(results: AnalysisResults, max_results: int = 20):
    """Print detailed results for the first few detections."""
    if not results.results:
        print("\nNo errors detected.")
        return
    
    print(f"\n" + "="*60)
    print("DETAILED RESULTS")
    print("="*60)
    
    for i, result in enumerate(results.results[:max_results]):
        print(f"\n[{i+1}] {result.error_type} (confidence: {result.confidence:.2f})")
        print(f"File: {result.file_path}:{result.line_number}")
        print(f"Line: {result.original_line}")
        print(f"Detector: {result.detector_name}")
        
        if result.context_before:
            print("Context before:")
            for line in result.context_before[-3:]:  # Show last 3 lines of context
                print(f"  {line}")
        
        if result.context_after:
            print("Context after:")
            for line in result.context_after[:3]:  # Show first 3 lines of context
                print(f"  {line}")
    
    if len(results.results) > max_results:
        print(f"\n... and {len(results.results) - max_results} more results.")
        print("Use --output to save all results to a file.")


def validate_args(args):
    """Validate command line arguments."""
    # Check input path
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input path does not exist: {args.input}")
        sys.exit(1)
    
    # Check confidence threshold
    if not 0.0 <= args.confidence_threshold <= 1.0:
        logger.error("Confidence threshold must be between 0.0 and 1.0")
        sys.exit(1)
    
    # Check context values
    if args.context_before < 0 or args.context_after < 0:
        logger.error("Context values must be non-negative")
        sys.exit(1)
    
    # Check parallel workers
    if args.parallel is not None and args.parallel < 1:
        logger.error("Number of parallel workers must be at least 1")
        sys.exit(1)
    
    # Check output format
    if args.format not in ['json', 'csv', 'msgpack']:
        logger.error("Output format must be one of: json, csv, msgpack")
        sys.exit(1)


def main():
    """Main entry point for the CLI application."""
    parser = argparse.ArgumentParser(
        description="Log Error Extractor - Advanced analysis of Ansible and system logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis of a single log file
  python -m src.main --input /var/log/ansible.log
  
  # Analyze a text file containing logs
  python -m src.main --input /tmp/debug.txt
  
  # Analyze all log and text files in a directory with ML clustering
  python -m src.main --input /var/log/ansible/ --output results.json --enable-clustering
  
  # Use enhanced hybrid detection with all ML capabilities
  python -m src.main --input logs/ --detector hybrid --confidence-threshold 0.8 --parallel 4
  
  # Use zero-shot classification for advanced error categorization
  python -m src.main --input app.log --detector zeroshot --confidence-threshold 0.7
  
  # Statistical anomaly detection for unusual patterns
  python -m src.main --input logs/ --detector statistical --z-threshold 2.5
  
  # Conservative hybrid mode requiring consensus from multiple detectors
  python -m src.main --input logs/ --detector hybrid --require-consensus
  
  # Extract more context and apply clustering
  python -m src.main --input app.log --context-before 10 --context-after 20 --enable-clustering
  
  # Advanced ML analysis with custom clustering parameters
  python -m src.main --input logs/ --detector hybrid --enable-clustering --clustering-eps 0.2
        """
    )
    
    # Input/Output arguments
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input file or directory path to analyze'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Output file path (if not specified, results are printed to console)'
    )
    
    parser.add_argument(
        '--format', '-f',
        choices=['json', 'csv', 'msgpack'],
        default='json',
        help='Output format (default: json)'
    )
    
    # Detector configuration  
    parser.add_argument(
        '--detector', '-d',
        choices=['pattern', 'semantic', 'zeroshot', 'statistical', 'hybrid'],
        default='hybrid',
        help='Detection method to use (default: hybrid)'
    )
    
    parser.add_argument(
        '--confidence-threshold', '-c',
        type=float,
        default=0.7,
        help='Minimum confidence threshold for detection (default: 0.7)'
    )
    
    parser.add_argument(
        '--config',
        help='Path to custom configuration file'
    )
    
    # Enhanced ML options
    parser.add_argument(
        '--enable-clustering',
        action='store_true',
        help='Enable ML-based error clustering to group similar errors'
    )
    
    parser.add_argument(
        '--clustering-eps',
        type=float,
        default=0.3,
        help='DBSCAN epsilon parameter for clustering (default: 0.3)'
    )
    
    parser.add_argument(
        '--clustering-min-samples',
        type=int,
        default=2,
        help='DBSCAN minimum samples parameter for clustering (default: 2)'
    )
    
    parser.add_argument(
        '--require-consensus',
        action='store_true',
        help='For hybrid detector: require multiple detectors to agree (more conservative)'
    )
    
    parser.add_argument(
        '--disable-zeroshot',
        action='store_true',
        help='Disable zero-shot classification in hybrid mode'
    )
    
    parser.add_argument(
        '--disable-statistical',
        action='store_true',
        help='Disable statistical anomaly detection in hybrid mode'
    )
    
    parser.add_argument(
        '--z-threshold',
        type=float,
        default=3.0,
        help='Z-score threshold for statistical anomaly detection (default: 3.0)'
    )
    
    parser.add_argument(
        '--min-samples',
        type=int,
        default=5,
        help='Minimum samples for statistical baseline (default: 5)'
    )
    
    # Context extraction settings
    parser.add_argument(
        '--context-before',
        type=int,
        default=5,
        help='Number of lines to include before error (default: 5)'
    )
    
    parser.add_argument(
        '--context-after',
        type=int,
        default=10,
        help='Number of lines to include after error (default: 10)'
    )
    
    # Processing options
    parser.add_argument(
        '--parallel', '-p',
        type=int,
        default=None,
        help='Number of parallel workers (default: auto-detect)'
    )
    
    parser.add_argument(
        '--pattern',
        default='*.{log,txt}',
        help='File pattern to match when processing directories (default: *.{log,txt})'
    )
    
    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help='Process directories recursively'
    )
    
    # Output options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress progress bars and non-essential output'
    )
    
    parser.add_argument(
        '--show-details',
        action='store_true',
        help='Show detailed results in console output'
    )
    
    parser.add_argument(
        '--max-results',
        type=int,
        default=20,
        help='Maximum number of detailed results to show (default: 20)'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Validate arguments
    validate_args(args)
    
    # Setup GPU acceleration if available
    setup_spacy_gpu()
    
    try:
        # Create detector with enhanced ML options
        logger.info(f"Initializing {args.detector} detector with confidence threshold {args.confidence_threshold}")
        detector_kwargs = {
            'z_threshold': args.z_threshold,
            'min_samples': args.min_samples,
            'require_consensus': args.require_consensus,
            'enable_zeroshot': not args.disable_zeroshot,
            'enable_statistical': not args.disable_statistical
        }
        
        detector = create_detector(
            detector_type=args.detector,
            confidence_threshold=args.confidence_threshold,
            config_path=args.config,
            enable_clustering=args.enable_clustering,
            **detector_kwargs
        )
        
        # Create context extractor
        context_extractor = ContextExtractor(
            context_before=args.context_before,
            context_after=args.context_after
        )
        
        # Create stream processor
        processor = StreamProcessor(
            detector=detector,
            context_extractor=context_extractor,
            parallel_workers=args.parallel
        )
        
        # Process input
        input_path = Path(args.input)
        start_time = time.time()
        
        if input_path.is_file():
            logger.info(f"Processing single file: {args.input}")
            results = processor.process_files([str(input_path)], show_progress=not args.quiet)
        elif input_path.is_dir():
            logger.info(f"Processing directory: {args.input}")
            results = processor.process_directory(
                directory_path=str(input_path),
                pattern=args.pattern,
                recursive=args.recursive,
                show_progress=not args.quiet
            )
        else:
            logger.error(f"Input path is neither a file nor directory: {args.input}")
            sys.exit(1)
        
        # Deduplicate results
        if results.results:
            original_count = len(results.results)
            results.deduplicate()
            dedup_count = len(results.results)
            if original_count != dedup_count:
                logger.info(f"Deduplicated {original_count - dedup_count} similar results")
        
        # Apply retry aggregation to reduce noise from multiple RETRYING lines
        if results.results:
            try:
                logger.info("Aggregating retry patterns...")
                from .processors import RetryAggregator
                retry_aggregator = RetryAggregator(min_retries=3)
                results = retry_aggregator.aggregate_retries(results)
                logger.info("Retry aggregation completed")
            except Exception as e:
                logger.warning(f"Error during retry aggregation: {e}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
        
        # Generate troubleshooting solutions for detected errors
        if results.results:
            try:
                logger.info("Generating troubleshooting solutions...")
                from .solutions import HybridSolutionEngine
                solution_engine = HybridSolutionEngine()
                
                # Generate solutions for each detection result
                enhanced_results = []
                for result in results.results:
                    # Convert DetectionResult to dict for solution engine
                    detection_dict = {
                        'original_line': result.original_line,
                        'error_type': result.error_type,
                        'confidence': result.confidence,
                        'matched_patterns': result.matched_patterns,
                        'detector_name': result.detector_name
                    }
                    
                    solutions = solution_engine.find_solutions(detection_dict)
                    
                    # Add solutions to the result
                    result.solutions = solutions
                    result.solution_source = "hybrid" if solutions else "none"
                    enhanced_results.append(result)
                
                results.results = enhanced_results
                solution_count = sum(1 for r in results.results if r.solutions)
                logger.info(f"Generated solutions for {solution_count}/{len(results.results)} errors")
                
            except Exception as e:
                logger.warning(f"Error during solution generation: {e}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
        
        # Apply ML-based clustering if enabled
        if args.enable_clustering and results.results and CLUSTERING_AVAILABLE:
            try:
                logger.info("Applying ML-based error clustering...")
                clusterer = ErrorClusterer(
                    eps=args.clustering_eps,
                    min_samples=args.clustering_min_samples
                )
                results = clusterer.apply_clustering_to_results(results)
                
                # Log clustering statistics
                cluster_stats = clusterer.get_clustering_statistics()
                logger.info(f"Clustering found {cluster_stats['total_clusters']} clusters "
                           f"with {cluster_stats['noise_points']} noise points")
                
            except Exception as e:
                logger.warning(f"Error during clustering: {e}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
        elif args.enable_clustering and not CLUSTERING_AVAILABLE:
            logger.warning("Clustering requested but scikit-learn not available. Install with: pip install scikit-learn")
        
        # Save results if output path specified
        if args.output:
            save_results(results, args.output, args.format)
        
        # Print summary
        if not args.quiet:
            print_summary(results)
            
            if args.show_details:
                print_detailed_results(results, args.max_results)
        
        # Print basic stats even in quiet mode
        if args.quiet and results.results:
            print(f"Found {len(results.results)} errors in {results.total_files_processed} files")
        
        # Exit with appropriate code
        sys.exit(0 if len(results.results) == 0 else 1)
        
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main() 