"""
Context extraction utility for capturing relevant log context around detected errors.
"""

from typing import List, Dict, Optional, Tuple, Set
from pathlib import Path
import mmap
from src.models.results import DetectionResult


class ContextExtractor:
    """Extracts context lines around detected errors with smart merging."""
    
    def __init__(self, context_before: int = 5, context_after: int = 10, 
                 max_context_lines: int = 50, merge_threshold: int = 3):
        """
        Initialize the context extractor.
        
        Args:
            context_before: Number of lines to include before the error
            context_after: Number of lines to include after the error
            max_context_lines: Maximum total context lines to extract
            merge_threshold: Merge contexts if errors are within this many lines
        """
        self.context_before = context_before
        self.context_after = context_after
        self.max_context_lines = max_context_lines
        self.merge_threshold = merge_threshold
    
    def extract_context_for_results(self, results: List[DetectionResult]) -> List[DetectionResult]:
        """
        Extract context for a list of detection results.
        
        Args:
            results: List of DetectionResult objects
            
        Returns:
            List of DetectionResult objects with context populated
        """
        if not results:
            return results
        
        # Group results by file for efficient processing
        results_by_file = {}
        for result in results:
            if result.file_path not in results_by_file:
                results_by_file[result.file_path] = []
            results_by_file[result.file_path].append(result)
        
        # Process each file
        updated_results = []
        for file_path, file_results in results_by_file.items():
            try:
                file_results_with_context = self._extract_context_for_file(file_path, file_results)
                updated_results.extend(file_results_with_context)
            except Exception as e:
                print(f"Warning: Could not extract context for {file_path}: {e}")
                # Return original results without context
                updated_results.extend(file_results)
        
        return updated_results
    
    def _extract_context_for_file(self, file_path: str, results: List[DetectionResult]) -> List[DetectionResult]:
        """
        Extract context for all results in a single file.
        
        Args:
            file_path: Path to the file
            results: List of DetectionResult objects for this file
            
        Returns:
            List of DetectionResult objects with context populated
        """
        if not results:
            return results
        
        # Sort results by line number for efficient processing
        sorted_results = sorted(results, key=lambda r: r.line_number)
        
        # Determine context ranges and merge overlapping ones
        context_ranges = self._calculate_context_ranges(sorted_results)
        
        # Read the file and extract context
        try:
            file_lines = self._read_file_lines(file_path)
            
            # Extract context for each range
            context_data = {}
            for start_line, end_line, result_indices in context_ranges:
                lines = self._extract_lines_range(file_lines, start_line, end_line)
                for result_index in result_indices:
                    result = sorted_results[result_index]
                    error_line_index = result.line_number - start_line
                    
                    # Split into before and after context
                    context_before = lines[:error_line_index] if error_line_index > 0 else []
                    context_after = lines[error_line_index + 1:] if error_line_index + 1 < len(lines) else []
                    
                    context_data[result_index] = {
                        'before': context_before,
                        'after': context_after
                    }
            
            # Update results with context
            for i, result in enumerate(sorted_results):
                if i in context_data:
                    result.context_before = context_data[i]['before']
                    result.context_after = context_data[i]['after']
            
            return sorted_results
            
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return results
    
    def _calculate_context_ranges(self, sorted_results: List[DetectionResult]) -> List[Tuple[int, int, List[int]]]:
        """
        Calculate context ranges for results, merging overlapping contexts.
        
        Args:
            sorted_results: Results sorted by line number
            
        Returns:
            List of (start_line, end_line, result_indices) tuples
        """
        if not sorted_results:
            return []
        
        ranges = []
        
        for i, result in enumerate(sorted_results):
            start_line = max(1, result.line_number - self.context_before)
            end_line = result.line_number + self.context_after
            ranges.append((start_line, end_line, [i]))
        
        # Merge overlapping ranges
        merged_ranges = []
        current_start, current_end, current_indices = ranges[0]
        
        for start, end, indices in ranges[1:]:
            # Check if ranges overlap or are close enough to merge
            if start <= current_end + self.merge_threshold:
                # Merge ranges
                current_end = max(current_end, end)
                current_indices.extend(indices)
            else:
                # Add current range and start new one
                merged_ranges.append((current_start, current_end, current_indices))
                current_start, current_end, current_indices = start, end, indices
        
        # Add the last range
        merged_ranges.append((current_start, current_end, current_indices))
        
        # Limit context size
        final_ranges = []
        for start, end, indices in merged_ranges:
            total_lines = end - start + 1
            if total_lines > self.max_context_lines:
                # Truncate context, keeping error lines in the middle
                error_lines = [sorted_results[i].line_number for i in indices]
                min_error = min(error_lines)
                max_error = max(error_lines)
                
                # Calculate how much context we can keep
                remaining_lines = self.max_context_lines - (max_error - min_error + 1)
                before_context = remaining_lines // 2
                after_context = remaining_lines - before_context
                
                new_start = max(start, min_error - before_context)
                new_end = min(end, max_error + after_context)
                
                final_ranges.append((new_start, new_end, indices))
            else:
                final_ranges.append((start, end, indices))
        
        return final_ranges
    
    def _read_file_lines(self, file_path: str) -> List[str]:
        """
        Read file lines efficiently, handling various encodings.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of file lines
        """
        encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    return f.readlines()
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error reading file {file_path} with encoding {encoding}: {e}")
                continue
        
        # Last resort: read as binary and decode with error replacement
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                decoded = content.decode('utf-8', errors='replace')
                return decoded.splitlines(keepends=True)
        except Exception as e:
            print(f"Could not read file {file_path}: {e}")
            return []
    
    def _extract_lines_range(self, file_lines: List[str], start_line: int, end_line: int) -> List[str]:
        """
        Extract a range of lines from the file lines list.
        
        Args:
            file_lines: List of all file lines
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (1-indexed)
            
        Returns:
            List of lines in the specified range
        """
        # Convert to 0-indexed
        start_idx = max(0, start_line - 1)
        end_idx = min(len(file_lines), end_line)
        
        lines = []
        for i in range(start_idx, end_idx):
            line = file_lines[i].rstrip('\n\r')
            lines.append(line)
        
        return lines
    
    def extract_context_streaming(self, file_path: str, results: List[DetectionResult], 
                                 buffer_size: int = 8192) -> List[DetectionResult]:
        """
        Extract context using streaming approach for very large files.
        
        Args:
            file_path: Path to the file
            results: List of DetectionResult objects
            buffer_size: Buffer size for reading
            
        Returns:
            List of DetectionResult objects with context populated
        """
        if not results:
            return results
        
        # Sort results by line number
        sorted_results = sorted(results, key=lambda r: r.line_number)
        
        # Calculate required line ranges
        context_ranges = self._calculate_context_ranges(sorted_results)
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                # Use memory mapping for large files
                if Path(file_path).stat().st_size > 100 * 1024 * 1024:  # 100MB
                    return self._extract_context_mmap(file_path, sorted_results, context_ranges)
                else:
                    return self._extract_context_for_file(file_path, results)
        
        except Exception as e:
            print(f"Error in streaming context extraction for {file_path}: {e}")
            return results
    
    def _extract_context_mmap(self, file_path: str, sorted_results: List[DetectionResult],
                             context_ranges: List[Tuple[int, int, List[int]]]) -> List[DetectionResult]:
        """
        Extract context using memory mapping for very large files.
        
        Args:
            file_path: Path to the file
            sorted_results: Results sorted by line number
            context_ranges: Pre-calculated context ranges
            
        Returns:
            List of DetectionResult objects with context populated
        """
        try:
            with open(file_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped_file:
                    # Build line index for efficient seeking
                    line_positions = self._build_line_index(mmapped_file)
                    
                    # Extract context for each range
                    context_data = {}
                    for start_line, end_line, result_indices in context_ranges:
                        lines = self._extract_lines_mmap(mmapped_file, line_positions, 
                                                       start_line, end_line)
                        
                        for result_index in result_indices:
                            result = sorted_results[result_index]
                            error_line_index = result.line_number - start_line
                            
                            context_before = lines[:error_line_index] if error_line_index > 0 else []
                            context_after = lines[error_line_index + 1:] if error_line_index + 1 < len(lines) else []
                            
                            context_data[result_index] = {
                                'before': context_before,
                                'after': context_after
                            }
                    
                    # Update results with context
                    for i, result in enumerate(sorted_results):
                        if i in context_data:
                            result.context_before = context_data[i]['before']
                            result.context_after = context_data[i]['after']
                    
                    return sorted_results
        
        except Exception as e:
            print(f"Error in mmap context extraction for {file_path}: {e}")
            return sorted_results
    
    def _build_line_index(self, mmapped_file: mmap.mmap) -> List[int]:
        """
        Build an index of line positions in the memory-mapped file.
        
        Args:
            mmapped_file: Memory-mapped file object
            
        Returns:
            List of byte positions for each line start
        """
        line_positions = [0]  # First line starts at position 0
        
        pos = 0
        while pos < len(mmapped_file):
            pos = mmapped_file.find(b'\n', pos)
            if pos == -1:
                break
            pos += 1  # Move past the newline
            line_positions.append(pos)
        
        return line_positions
    
    def _extract_lines_mmap(self, mmapped_file: mmap.mmap, line_positions: List[int],
                           start_line: int, end_line: int) -> List[str]:
        """
        Extract lines from memory-mapped file using line index.
        
        Args:
            mmapped_file: Memory-mapped file object
            line_positions: List of line start positions
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (1-indexed)
            
        Returns:
            List of extracted lines
        """
        lines = []
        
        # Convert to 0-indexed
        start_idx = max(0, start_line - 1)
        end_idx = min(len(line_positions) - 1, end_line - 1)
        
        for i in range(start_idx, end_idx + 1):
            if i < len(line_positions) - 1:
                start_pos = line_positions[i]
                end_pos = line_positions[i + 1] - 1  # Exclude the newline
            else:
                start_pos = line_positions[i]
                end_pos = len(mmapped_file)
            
            if start_pos < end_pos:
                line_bytes = mmapped_file[start_pos:end_pos]
                try:
                    line = line_bytes.decode('utf-8', errors='replace').rstrip('\n\r')
                    lines.append(line)
                except UnicodeDecodeError:
                    lines.append(f"<binary data at line {i + 1}>")
        
        return lines
    
    def get_context_summary(self, results: List[DetectionResult]) -> Dict:
        """
        Get a summary of context extraction statistics.
        
        Args:
            results: List of DetectionResult objects
            
        Returns:
            Dictionary with context statistics
        """
        total_results = len(results)
        results_with_context_before = sum(1 for r in results if r.context_before)
        results_with_context_after = sum(1 for r in results if r.context_after)
        
        avg_context_before = (sum(len(r.context_before) for r in results) / total_results
                             if total_results > 0 else 0)
        avg_context_after = (sum(len(r.context_after) for r in results) / total_results
                            if total_results > 0 else 0)
        
        return {
            'total_results': total_results,
            'results_with_context_before': results_with_context_before,
            'results_with_context_after': results_with_context_after,
            'avg_context_before_lines': avg_context_before,
            'avg_context_after_lines': avg_context_after,
            'context_settings': {
                'context_before': self.context_before,
                'context_after': self.context_after,
                'max_context_lines': self.max_context_lines,
                'merge_threshold': self.merge_threshold
            }
        } 