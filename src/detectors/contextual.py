"""
Contextual Correlation Detector for Smart-Chunking Log Analysis.

This detector identifies infrastructure correlations, multi-line patterns,
and contextual relationships that single-line detectors miss.

Key Features:
- Infrastructure lifecycle correlation (EC2 stop/start -> SSH failures)
- Boot sequence intelligence (system boot -> access denied)
- SSH provisioning correlation (key missing after restart)
- Critical path dependency analysis (bastion down -> playbook blocked)
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict, deque

from .base import BaseDetector
from ..models.results import DetectionResult

logger = logging.getLogger(__name__)


@dataclass
class ContextualEvent:
    """Represents an event in the contextual analysis."""
    line_number: int
    content: str
    event_type: str
    timestamp: Optional[str] = None
    host: Optional[str] = None
    confidence: float = 0.0


class ContextualCorrelationDetector(BaseDetector):
    """
    Advanced detector for infrastructure correlations and contextual patterns.
    
    This detector maintains a sliding window of events and identifies patterns
    that span multiple lines and require contextual understanding.
    """
    
    def __init__(self, config_path: str = "config/patterns.yaml", window_size: int = 50):
        """
        Initialize contextual correlation detector.
        
        Args:
            config_path: Path to patterns configuration
            window_size: Number of lines to keep in sliding window for correlation
        """
        super().__init__(config_path)
        self.window_size = window_size
        self.event_window = deque(maxlen=window_size)
        self.correlation_patterns = self._load_correlation_patterns()
        
    def _load_correlation_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load correlation patterns from configuration."""
        patterns = {}
        
        # Infrastructure correlation patterns
        patterns['ec2_restart_ssh_failure'] = {
            'trigger_patterns': [
                r'Ensure EC2 instances are running',
                r'changed:.*item.*state.*stopped',
                r'Wait until all EC2 instances are running'
            ],
            'consequence_patterns': [
                r'UNREACHABLE!',
                r'no such identity:',
                r'System is booting up',
                r'Failed to connect to the host via ssh'
            ],
            'window_size': 30,
            'confidence': 0.92,
            'category': 'infrastructure_correlation'
        }
        
        # Boot sequence correlation
        patterns['boot_sequence_timing'] = {
            'trigger_patterns': [
                r'System is booting up',
                r'Unprivileged users are not permitted to log in yet'
            ],
            'consequence_patterns': [
                r'UNREACHABLE!',
                r'Connection.*refused',
                r'Permission denied'
            ],
            'window_size': 10,
            'confidence': 0.95,
            'category': 'boot_sequence_intelligence'
        }
        
        # SSH provisioning correlation
        patterns['ssh_key_provisioning'] = {
            'trigger_patterns': [
                r'ssh_provision_\w+',
                r'Generate SSH keys',
                r'SSH.*provision'
            ],
            'consequence_patterns': [
                r'no such identity:',
                r'ssh_provision_.*: No such file or directory',
                r'Permission denied.*publickey'
            ],
            'window_size': 25,
            'confidence': 0.90,
            'category': 'ssh_provisioning_correlation'
        }
        
        # Critical dependency failure
        patterns['critical_dependency'] = {
            'trigger_patterns': [
                r'bastion.*unreachable',
                r'.*unreachable=1.*',
                r'NO MORE HOSTS LEFT'
            ],
            'consequence_patterns': [
                r'All hosts unreachable',
                r'Playbook.*failed',
                r'Fatal.*execution'
            ],
            'window_size': 5,
            'confidence': 0.98,
            'category': 'critical_dependency'
        }
        
        return patterns
    
    def detect_errors(self, file_path: str, lines: List[str]) -> List[DetectionResult]:
        """
        Detect contextual correlations and infrastructure patterns.
        
        Args:
            file_path: Path to the file being analyzed
            lines: List of log lines to analyze
            
        Returns:
            List of DetectionResult objects for correlated patterns
        """
        results = []
        self.event_window.clear()
        
        # First pass: identify individual events and build context window
        events = self._extract_events(lines)
        
        # Second pass: identify correlations
        correlations = self._identify_correlations(events)
        
        # Convert correlations to detection results
        for correlation in correlations:
            result = DetectionResult(
                file_path=file_path,
                line_number=correlation['primary_line'],
                original_line=correlation['primary_content'],
                error_type=correlation['correlation_type'],
                confidence=correlation['confidence'],
                detector_name='contextual_correlation',
                matched_patterns=correlation.get('matched_patterns', []),
                context_before=correlation.get('context_before', []),
                context_after=correlation.get('context_after', [])
            )
            
            # Add correlation metadata
            result.correlation_metadata = {
                'trigger_line': correlation.get('trigger_line'),
                'trigger_content': correlation.get('trigger_content'),
                'consequence_line': correlation['primary_line'],
                'consequence_content': correlation['primary_content'],
                'correlation_distance': correlation.get('distance', 0),
                'infrastructure_impact': correlation.get('impact', 'UNKNOWN')
            }
            
            results.append(result)
            
        logger.info(f"Contextual detector found {len(results)} correlations in {file_path}")
        return results
    
    def _extract_events(self, lines: List[str]) -> List[ContextualEvent]:
        """Extract relevant events from log lines."""
        events = []
        
        for line_num, line in enumerate(lines, 1):
            # Extract timestamp if present
            timestamp = self._extract_timestamp(line)
            
            # Extract host if present
            host = self._extract_host(line)
            
            # Check for infrastructure events
            event_type = self._classify_event(line)
            
            if event_type:
                event = ContextualEvent(
                    line_number=line_num,
                    content=line,
                    event_type=event_type,
                    timestamp=timestamp,
                    host=host
                )
                events.append(event)
        
        return events
    
    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from log line."""
        # Match Ansible timestamp format: "Friday 18 July 2025  21:02:24 +0000"
        timestamp_pattern = r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+[+-]\d{4})'
        match = re.search(timestamp_pattern, line)
        return match.group(1) if match else None
    
    def _extract_host(self, line: str) -> Optional[str]:
        """Extract host information from log line."""
        # Match Ansible host patterns: [hostname] or hostname:
        host_patterns = [
            r'\[([^\]]+)\]',  # [bastion.25cj7.internal]
            r'^(\w+\.\w+\.\w+):',  # bastion.25cj7.internal:
            r'item=.*Name.*:\s*([^,}]+)'  # Extract from EC2 instance data
        ]
        
        for pattern in host_patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(1)
        
        return None
    
    def _classify_event(self, line: str) -> Optional[str]:
        """Classify the type of event based on line content."""
        event_classifications = {
            'ec2_lifecycle': [
                r'Ensure EC2 instances are running',
                r'changed:.*item.*state.*stopped',
                r'Wait until all EC2 instances are running',
                r'EC2 instances.*running'
            ],
            'ssh_failure': [
                r'UNREACHABLE!',
                r'Failed to connect to the host via ssh',
                r'Connection.*refused',
                r'ssh.*authentication.*failed'
            ],
            'boot_sequence': [
                r'System is booting up',
                r'Unprivileged users are not permitted to log in yet',
                r'Please come back later'
            ],
            'ssh_provisioning': [
                r'no such identity:',
                r'ssh_provision_.*: No such file or directory',
                r'Generate SSH keys',
                r'SSH.*provision'
            ],
            'critical_failure': [
                r'bastion.*unreachable',
                r'.*unreachable=1.*',
                r'NO MORE HOSTS LEFT',
                r'All hosts unreachable'
            ]
        }
        
        for event_type, patterns in event_classifications.items():
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    return event_type
        
        return None
    
    def _identify_correlations(self, events: List[ContextualEvent]) -> List[Dict[str, Any]]:
        """Identify correlations between events."""
        correlations = []
        
        for i, event in enumerate(events):
            # Look for correlations based on our patterns
            for pattern_name, pattern_config in self.correlation_patterns.items():
                correlation = self._check_correlation(
                    event, events, i, pattern_name, pattern_config
                )
                if correlation:
                    correlations.append(correlation)
        
        return correlations
    
    def _check_correlation(self, primary_event: ContextualEvent, all_events: List[ContextualEvent], 
                          primary_index: int, pattern_name: str, pattern_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check if a specific correlation pattern exists."""
        window_size = pattern_config.get('window_size', 20)
        
        # Check if primary event matches consequence patterns
        consequence_match = False
        for pattern in pattern_config['consequence_patterns']:
            if re.search(pattern, primary_event.content, re.IGNORECASE):
                consequence_match = True
                break
        
        if not consequence_match:
            return None
        
        # Look backward for trigger patterns
        start_index = max(0, primary_index - window_size)
        for j in range(start_index, primary_index):
            trigger_event = all_events[j]
            
            for trigger_pattern in pattern_config['trigger_patterns']:
                if re.search(trigger_pattern, trigger_event.content, re.IGNORECASE):
                    # Found correlation!
                    return {
                        'correlation_type': f"{pattern_name}_correlation",
                        'primary_line': primary_event.line_number,
                        'primary_content': primary_event.content,
                        'trigger_line': trigger_event.line_number,
                        'trigger_content': trigger_event.content,
                        'confidence': pattern_config['confidence'],
                        'distance': primary_index - j,
                        'matched_patterns': [trigger_pattern],
                        'category': pattern_config['category'],
                        'impact': self._assess_impact(pattern_name, primary_event, trigger_event)
                    }
        
        return None
    
    def _assess_impact(self, pattern_name: str, primary_event: ContextualEvent, trigger_event: ContextualEvent) -> str:
        """Assess the impact level of the correlation."""
        impact_levels = {
            'ec2_restart_ssh_failure': 'HIGH',
            'boot_sequence_timing': 'MEDIUM', 
            'ssh_key_provisioning': 'HIGH',
            'critical_dependency': 'CRITICAL'
        }
        
        return impact_levels.get(pattern_name, 'UNKNOWN')

    def detect(self, line: str, line_number: int, file_path: str) -> Optional[DetectionResult]:
        """
        Single line detection (not used for contextual analysis).
        
        The contextual detector requires full file analysis, so this method
        returns None. Use detect_errors() for full file analysis.
        """
        return None
    
    def get_confidence(self, line: str) -> float:
        """
        Get confidence score for a single line.
        
        Since contextual analysis requires multiple lines, this returns
        a base confidence that will be overridden by correlation analysis.
        """
        # Check if line matches any of our event types
        event_type = self._classify_event(line)
        if event_type:
            return 0.6  # Base confidence for individual events
        return 0.0
    
    def get_error_type(self, line: str) -> str:
        """
        Determine error type for a single line.
        
        This is used as a fallback, but contextual analysis provides
        more detailed correlation types.
        """
        event_type = self._classify_event(line)
        if event_type:
            return f"infrastructure_{event_type}"
        return "unknown"

    def get_detector_info(self) -> Dict[str, Any]:
        """Get information about this detector."""
        return {
            "name": "contextual_correlation",
            "description": "Advanced infrastructure correlation and contextual pattern detector",
            "version": "1.0.0",
            "capabilities": [
                "infrastructure_lifecycle_correlation",
                "boot_sequence_intelligence", 
                "ssh_provisioning_correlation",
                "critical_dependency_analysis",
                "multi_line_pattern_detection"
            ],
            "window_size": self.window_size,
            "correlation_patterns": len(self.correlation_patterns)
        } 