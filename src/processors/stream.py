"""
Stream processor for efficient processing of large log files with multiprocessing support.
"""

import os
import sys
from pathlib import Path
from typing import List, Generator, Iterator, Optional, Callable, Dict, Any
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
from collections import deque
import mmap
from tqdm import tqdm
import platform

from ..detectors.base import BaseDetector
from ..models.results import DetectionResult, AnalysisResults
from .context import ContextExtractor


def process_file_chunk(args):
    """
    Process a chunk of files - used for multiprocessing.
    
    Args:
        args: Tuple of (detector_class, detector_args, file_paths, context_extractor_args)
        
    Returns:
        AnalysisResults object
    """
    detector_class, detector_args, file_paths, context_extractor_args = args
    
    # Initialize detector in the worker process
    detector = detector_class(**detector_args)
    detector.setup()
    
    # Initialize context extractor
    context_extractor = ContextExtractor(**context_extractor_args) if context_extractor_args else None
    
    # Initialize results
    results = AnalysisResults()
    
    try:
        for file_path in file_paths:
            try:
                file_results = process_single_file(file_path, detector)
                results.results.extend(file_results)
                results.total_files_processed += 1
                
                # Count lines processed (estimate)
                if file_results:
                    max_line = max(r.line_number for r in file_results)
                    results.total_lines_processed += max_line
                else:
                    # Estimate lines for files with no detections
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            lines = sum(1 for _ in f)
                            results.total_lines_processed += lines
                    except:
                        pass
                        
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")
                continue
        
        # Extract context if needed
        if context_extractor and results.results:
            results.results = context_extractor.extract_context_for_results(results.results)
    
    finally:
        detector.cleanup()
    
    return results


def process_single_file(file_path: str, detector: BaseDetector) -> List[DetectionResult]:
    """
    Process a single file and return detection results.
    
    Args:
        file_path: Path to the file to process
        detector: Detector instance to use
        
    Returns:
        List of DetectionResult objects
    """
    results = []
    
    try:
        # Determine file size to choose processing strategy
        file_size = Path(file_path).stat().st_size
        
        if file_size > 100 * 1024 * 1024:  # 100MB
            # Use memory mapping for very large files
            results = process_large_file_mmap(file_path, detector)
        elif file_size > 10 * 1024 * 1024:  # 10MB
            # Use streaming for medium files
            results = process_file_streaming(file_path, detector)
        else:
            # Use regular processing for small files
            results = process_file_regular(file_path, detector)
    
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
    
    return results


def process_file_regular(file_path: str, detector: BaseDetector) -> List[DetectionResult]:
    """Process a regular-sized file by reading all lines into memory."""
    results = []
    
    encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                lines = f.readlines()
                
                # Process lines in batches for efficiency
                batch_size = 1000
                for i in range(0, len(lines), batch_size):
                    batch_lines = [(lines[j].rstrip('\n\r'), j + 1) 
                                  for j in range(i, min(i + batch_size, len(lines)))]
                    
                    batch_results = detector.batch_detect(batch_lines, file_path)
                    results.extend(batch_results)
                
                break  # Successfully processed with this encoding
                
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Error reading file {file_path} with encoding {encoding}: {e}")
            break
    
    return results


def process_file_streaming(file_path: str, detector: BaseDetector) -> List[DetectionResult]:
    """Process a medium-sized file using streaming approach."""
    results = []
    buffer_size = 8192
    batch_size = 100
    
    encodings = ['utf-8', 'latin-1', 'cp1252']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace', buffering=buffer_size) as f:
                line_buffer = []
                line_number = 0
                
                for line in f:
                    line_number += 1
                    line_content = line.rstrip('\n\r')
                    
                    # Quick filter to skip obviously irrelevant lines
                    if detector.should_detect(line_content):
                        line_buffer.append((line_content, line_number))
                    
                    # Process batch when buffer is full
                    if len(line_buffer) >= batch_size:
                        batch_results = detector.batch_detect(line_buffer, file_path)
                        results.extend(batch_results)
                        line_buffer.clear()
                
                # Process remaining lines
                if line_buffer:
                    batch_results = detector.batch_detect(line_buffer, file_path)
                    results.extend(batch_results)
                
                break  # Successfully processed
                
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Error streaming file {file_path} with encoding {encoding}: {e}")
            break
    
    return results


def process_large_file_mmap(file_path: str, detector: BaseDetector) -> List[DetectionResult]:
    """Process a large file using memory mapping."""
    results = []
    
    try:
        with open(file_path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped_file:
                line_number = 0
                line_buffer = []
                batch_size = 100
                
                # Read line by line from memory mapped file
                current_line = bytearray()
                pos = 0
                
                while pos < len(mmapped_file):
                    byte = mmapped_file[pos:pos+1]
                    pos += 1
                    
                    if byte == b'\n':
                        # End of line
                        line_number += 1
                        try:
                            line_content = current_line.decode('utf-8', errors='replace').rstrip('\r')
                            
                            if detector.should_detect(line_content):
                                line_buffer.append((line_content, line_number))
                            
                            # Process batch
                            if len(line_buffer) >= batch_size:
                                batch_results = detector.batch_detect(line_buffer, file_path)
                                results.extend(batch_results)
                                line_buffer.clear()
                            
                        except Exception as e:
                            # Skip problematic lines
                            pass
                        
                        current_line.clear()
                    else:
                        current_line.extend(byte)
                
                # Process last line if exists
                if current_line:
                    line_number += 1
                    try:
                        line_content = current_line.decode('utf-8', errors='replace').rstrip('\r')
                        if detector.should_detect(line_content):
                            line_buffer.append((line_content, line_number))
                    except:
                        pass
                
                # Process remaining lines
                if line_buffer:
                    batch_results = detector.batch_detect(line_buffer, file_path)
                    results.extend(batch_results)
    
    except Exception as e:
        print(f"Error processing large file {file_path} with mmap: {e}")
    
    return results


class StreamProcessor:
    """Main stream processor for handling multiple files with multiprocessing."""
    
    def __init__(self, detector: BaseDetector, context_extractor: Optional[ContextExtractor] = None,
                 parallel_workers: int = None, chunk_size: int = 10):
        """
        Initialize the stream processor.
        
        Args:
            detector: The detector to use for error detection
            context_extractor: Optional context extractor
            parallel_workers: Number of parallel workers (None for auto-detect)
            chunk_size: Number of files per worker chunk
        """
        self.detector = detector
        self.context_extractor = context_extractor
        self.parallel_workers = parallel_workers or max(1, mp.cpu_count() - 1)
        self.chunk_size = chunk_size
        
        # Set up multiprocessing context for CUDA compatibility
        self.mp_context = self._setup_multiprocessing_context(detector)
        
        # Statistics
        self.stats = {
            'files_processed': 0,
            'lines_processed': 0,
            'errors_found': 0,
            'processing_time': 0.0,
            'files_skipped': 0
        }
    
    def _setup_multiprocessing_context(self, detector: BaseDetector):
        """
        Set up appropriate multiprocessing context based on detector type.
        
        Args:
            detector: The detector instance
            
        Returns:
            Multiprocessing context
        """
        # Check if detector uses CUDA/GPU (semantic or hybrid detectors)
        detector_name = detector.__class__.__name__.lower()
        uses_cuda = 'semantic' in detector_name or 'hybrid' in detector_name
        
        # On Unix systems, use 'spawn' method for CUDA compatibility
        if uses_cuda and platform.system() != 'Windows':
            print("Using 'spawn' multiprocessing for CUDA compatibility")
            return mp.get_context('spawn')
        else:
            # Use default context for pattern-only detection
            return mp.get_context()
    
    def process_files(self, file_paths: List[str], show_progress: bool = True) -> AnalysisResults:
        """
        Process multiple files and return combined results.
        
        Args:
            file_paths: List of file paths to process
            show_progress: Whether to show progress bar
            
        Returns:
            AnalysisResults object with combined results
        """
        start_time = time.time()
        
        # Filter valid files
        valid_files = self._filter_valid_files(file_paths)
        
        if not valid_files:
            print("No valid files to process.")
            return AnalysisResults()
        
        print(f"Processing {len(valid_files)} files with {self.parallel_workers} workers...")
        
        # Prepare detector arguments for multiprocessing
        detector_class = self.detector.__class__
        detector_args = {
            'confidence_threshold': self.detector.confidence_threshold
        }
        
        # Add detector-specific arguments
        if hasattr(self.detector, 'config'):
            detector_args['config_path'] = None  # Will use default config
        
        context_extractor_args = None
        if self.context_extractor:
            context_extractor_args = {
                'context_before': self.context_extractor.context_before,
                'context_after': self.context_extractor.context_after,
                'max_context_lines': self.context_extractor.max_context_lines,
                'merge_threshold': self.context_extractor.merge_threshold
            }
        
        # Split files into chunks for parallel processing
        file_chunks = self._chunk_files(valid_files, self.chunk_size)
        
        # Process files in parallel
        combined_results = AnalysisResults()
        
        if self.parallel_workers == 1:
            # Single-threaded processing
            for chunk in tqdm(file_chunks, desc="Processing file chunks", disable=not show_progress):
                args = (detector_class, detector_args, chunk, context_extractor_args)
                chunk_results = process_file_chunk(args)
                self._merge_results(combined_results, chunk_results)
        else:
            # Multi-threaded processing with appropriate context
            with ProcessPoolExecutor(max_workers=self.parallel_workers, mp_context=self.mp_context) as executor:
                # Submit all chunks
                future_to_chunk = {}
                for chunk in file_chunks:
                    args = (detector_class, detector_args, chunk, context_extractor_args)
                    future = executor.submit(process_file_chunk, args)
                    future_to_chunk[future] = chunk
                
                # Collect results with progress bar
                progress_bar = tqdm(total=len(file_chunks), desc="Processing file chunks", 
                                  disable=not show_progress)
                
                for future in as_completed(future_to_chunk):
                    try:
                        chunk_results = future.result()
                        self._merge_results(combined_results, chunk_results)
                        progress_bar.update(1)
                    except Exception as e:
                        chunk = future_to_chunk[future]
                        print(f"Error processing chunk {chunk}: {e}")
                        progress_bar.update(1)
                
                progress_bar.close()
        
        # Update final statistics
        end_time = time.time()
        combined_results.processing_time = end_time - start_time
        
        print(f"\nProcessing complete!")
        print(f"Files processed: {combined_results.total_files_processed}")
        print(f"Lines processed: {combined_results.total_lines_processed}")
        print(f"Errors found: {len(combined_results.results)}")
        print(f"Processing time: {combined_results.processing_time:.2f} seconds")
        
        return combined_results
    
    def process_directory(self, directory_path: str, pattern: str = "*.{log,txt}", 
                         recursive: bool = True, show_progress: bool = True) -> AnalysisResults:
        """
        Process all files in a directory matching a pattern.
        
        Args:
            directory_path: Path to the directory
            pattern: File pattern to match (e.g., "*.{log,txt}", "*.log", "*.txt")
            recursive: Whether to search subdirectories
            show_progress: Whether to show progress bar
            
        Returns:
            AnalysisResults object
        """
        dir_path = Path(directory_path)
        
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"Directory does not exist: {directory_path}")
        
        # Find matching files
        files = []
        
        # Handle brace expansion patterns like *.{log,txt}
        if '{' in pattern and '}' in pattern:
            # Extract extensions from brace pattern
            import re
            match = re.search(r'\*\.{([^}]+)}', pattern)
            if match:
                extensions = match.group(1).split(',')
                for ext in extensions:
                    ext_pattern = f"*.{ext.strip()}"
                    if recursive:
                        files.extend(dir_path.rglob(ext_pattern))
                    else:
                        files.extend(dir_path.glob(ext_pattern))
            else:
                # Fallback to original pattern
                if recursive:
                    files = list(dir_path.rglob(pattern))
                else:
                    files = list(dir_path.glob(pattern))
        else:
            # Standard pattern matching
            if recursive:
                files = list(dir_path.rglob(pattern))
            else:
                files = list(dir_path.glob(pattern))
        
        file_paths = [str(f) for f in files if f.is_file()]
        
        print(f"Found {len(file_paths)} files matching pattern '{pattern}' in {directory_path}")
        
        return self.process_files(file_paths, show_progress)
    
    def _filter_valid_files(self, file_paths: List[str]) -> List[str]:
        """Filter out invalid or unreadable files."""
        valid_files = []
        ignored_extensions = {'.gz', '.zip', '.tar', '.bz2', '.binary', '.exe', '.so', '.dll'}
        
        for file_path in file_paths:
            path = Path(file_path)
            
            # Check if file exists and is readable
            if not path.exists() or not path.is_file():
                print(f"Skipping non-existent file: {file_path}")
                continue
            
            # Skip binary files based on extension
            if path.suffix.lower() in ignored_extensions:
                print(f"Skipping binary file: {file_path}")
                continue
            
            # Check file size (skip empty files)
            try:
                if path.stat().st_size == 0:
                    print(f"Skipping empty file: {file_path}")
                    continue
            except OSError:
                print(f"Cannot access file: {file_path}")
                continue
            
            valid_files.append(file_path)
        
        return valid_files
    
    def _chunk_files(self, file_paths: List[str], chunk_size: int) -> List[List[str]]:
        """Split files into chunks for parallel processing."""
        chunks = []
        for i in range(0, len(file_paths), chunk_size):
            chunk = file_paths[i:i + chunk_size]
            chunks.append(chunk)
        return chunks
    
    def _merge_results(self, combined_results: AnalysisResults, chunk_results: AnalysisResults) -> None:
        """Merge chunk results into combined results."""
        combined_results.results.extend(chunk_results.results)
        combined_results.total_files_processed += chunk_results.total_files_processed
        combined_results.total_lines_processed += chunk_results.total_lines_processed
        
        # Merge detector stats
        for detector, count in chunk_results.detector_stats.items():
            combined_results.detector_stats[detector] = (
                combined_results.detector_stats.get(detector, 0) + count
            )
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return self.stats.copy()
    
    def estimate_processing_time(self, file_paths: List[str]) -> float:
        """
        Estimate processing time based on file sizes and past performance.
        
        Args:
            file_paths: List of file paths
            
        Returns:
            Estimated processing time in seconds
        """
        total_size = 0
        valid_files = self._filter_valid_files(file_paths)
        
        for file_path in valid_files:
            try:
                size = Path(file_path).stat().st_size
                total_size += size
            except OSError:
                continue
        
        # Rough estimate: 10MB per second per worker
        bytes_per_second_per_worker = 10 * 1024 * 1024
        total_throughput = bytes_per_second_per_worker * self.parallel_workers
        
        estimated_time = total_size / total_throughput
        
        # Add overhead for processing and context extraction
        overhead_factor = 1.5 if self.context_extractor else 1.2
        
        return estimated_time * overhead_factor 