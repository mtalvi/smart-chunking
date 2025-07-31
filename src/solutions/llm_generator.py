"""
LLM-based solution generator for Ansible log analysis.

This module provides intelligent solution generation using Llama 3.1 for unknown/complex errors.
Part of the Hybrid Troubleshooting Support Strategy (ADR-001 Decision #6).
"""

import requests
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class LLMSolutionGenerator:
    """LLM-powered solution generation for unknown/complex errors."""
    
    def __init__(self, ollama_url: str = "http://localhost:11434", 
                 model_name: str = "llama3.1:8b-instruct-q4_0",
                 timeout: int = 30):
        """
        Initialize the LLM solution generator.
        
        Args:
            ollama_url: URL of the Ollama server
            model_name: Name of the LLM model to use
            timeout: Request timeout in seconds
        """
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.timeout = timeout
        
        self.stats = {
            'solutions_generated': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'timeouts': 0,
            'total_response_time': 0.0
        }
        
        # Test connection on initialization
        self.is_available = self._test_connection()
    
    def _test_connection(self) -> bool:
        """Test connection to Ollama server."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [model['name'] for model in models]
                
                if self.model_name in model_names:
                    logger.info(f"LLM solution generator initialized: {self.model_name} available")
                    return True
                else:
                    logger.warning(f"Model {self.model_name} not found. Available models: {model_names}")
                    return False
            else:
                logger.warning(f"Ollama server not responding properly: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama server not available - LLM solutions disabled")
            return False
        except Exception as e:
            logger.warning(f"Error testing LLM connection: {e}")
            return False
    
    def generate_solutions(self, detection_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate solutions using LLM for detection results.
        
        Args:
            detection_result: Detection result from smart-chunking system
            
        Returns:
            List of LLM-generated solutions
        """
        if not self.is_available:
            logger.debug("LLM not available, skipping solution generation")
            return []
        
        error_line = detection_result.get('original_line', '')
        error_type = detection_result.get('error_type', '')
        context_before = detection_result.get('context_before', [])
        context_after = detection_result.get('context_after', [])
        confidence = detection_result.get('confidence', 0.0)
        
        if not error_line:
            return []
        
        # Create focused prompt for solution generation
        prompt = self._create_solution_prompt(
            error_line, error_type, context_before, context_after, confidence
        )
        
        try:
            start_time = datetime.now()
            solutions = self._call_llm_for_solutions(prompt)
            end_time = datetime.now()
            
            response_time = (end_time - start_time).total_seconds()
            self.stats['total_response_time'] += response_time
            self.stats['successful_requests'] += 1
            
            if solutions:
                self.stats['solutions_generated'] += len(solutions)
                logger.debug(f"Generated {len(solutions)} LLM solutions in {response_time:.2f}s")
            
            return solutions
            
        except requests.exceptions.Timeout:
            logger.warning("LLM request timeout - CPU processing taking too long")
            self.stats['timeouts'] += 1
            return self._get_fallback_solutions(detection_result)
            
        except Exception as e:
            logger.warning(f"LLM solution generation failed: {e}")
            self.stats['failed_requests'] += 1
            return self._get_fallback_solutions(detection_result)
    
    def _create_solution_prompt(self, error_line: str, error_type: str, 
                              context_before: List[str], context_after: List[str], 
                              confidence: float) -> str:
        """Create focused prompt for solution generation."""
        
        # Build context information
        context_info = ""
        if context_before:
            context_info += f"Context before error:\n{chr(10).join(context_before[-2:])}\n\n"
        
        context_info += f"ERROR: {error_line}\n\n"
        
        if context_after:
            context_info += f"Context after error:\n{chr(10).join(context_after[:2])}\n\n"
        
        # Create solution-focused prompt
        prompt = f"""You are an expert Ansible troubleshooter. Analyze this error and provide 2-3 specific, actionable solutions.

{context_info}Error Type: {error_type}
Detection Confidence: {confidence*100:.1f}%

Provide solutions in this EXACT JSON format:
{{
  "solutions": [
    {{
      "title": "Most Likely Solution Title",
      "confidence": 0.85,
      "steps": [
        "Step 1: Specific command or action",
        "Step 2: Another specific action",
        "Step 3: Verification step"
      ],
      "category": "category_name",
      "estimated_fix_time": "5-10 minutes"
    }}
  ]
}}

Focus on:
- Actionable steps with specific commands
- Root cause analysis based on the error
- Time estimates for each solution
- High confidence scores for well-known fixes

JSON response only:"""
        
        return prompt
    
    def _call_llm_for_solutions(self, prompt: str) -> List[Dict[str, Any]]:
        """Call LLM API to generate solutions."""
        request_payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,  # Lower temperature for more focused responses
                "num_ctx": 4096,     # Context window
                "num_predict": 800,  # Limit response length
                "top_p": 0.9,
                "repeat_penalty": 1.1
            }
        }
        
        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json=request_payload,
            timeout=self.timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"LLM API error: {response.status_code}")
        
        result = response.json()
        llm_response = result.get('response', '').strip()
        
        # Parse JSON response
        solutions = self._parse_llm_response(llm_response)
        return solutions
    
    def _parse_llm_response(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse LLM JSON response into solutions."""
        try:
            # Try to extract JSON from response
            json_start = llm_response.find('{')
            json_end = llm_response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                parsed = json.loads(json_str)
                
                solutions = parsed.get('solutions', [])
                
                # Enhance solutions with LLM metadata
                for solution in solutions:
                    solution.update({
                        'type': 'llm_generated',
                        'source': 'llama3.1',
                        'generated_at': datetime.now().isoformat()
                    })
                
                return solutions
            else:
                raise ValueError("No valid JSON found in response")
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Raw response: {llm_response[:200]}...")
            return self._extract_fallback_solution(llm_response)
        except Exception as e:
            logger.warning(f"Error parsing LLM response: {e}")
            return []
    
    def _extract_fallback_solution(self, response: str) -> List[Dict[str, Any]]:
        """Extract solution from non-JSON response as fallback."""
        # Simple text parsing as fallback
        lines = response.strip().split('\n')
        steps = []
        
        for line in lines:
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('•') or 
                        line.startswith('1.') or line.startswith('Step')):
                # Clean up step text
                clean_step = line.lstrip('-•123456789. ').strip()
                if clean_step:
                    steps.append(clean_step)
        
        if steps:
            return [{
                'title': 'LLM Generated Solution',
                'confidence': 0.6,
                'steps': steps[:5],  # Limit to 5 steps
                'category': 'llm_general',
                'type': 'llm_generated',
                'source': 'llama3.1_fallback',
                'estimated_fix_time': '10-20 minutes'
            }]
        
        return []
    
    def _get_fallback_solutions(self, detection_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Provide fallback solutions when LLM is unavailable."""
        error_type = detection_result.get('error_type', '').lower()
        
        # Basic fallback solutions based on error type
        fallback_solutions = {
            'fatal': {
                'title': 'General Fatal Error Troubleshooting',
                'steps': [
                    'Check the full error message and context',
                    'Verify target host connectivity and accessibility',
                    'Review Ansible playbook syntax and configuration',
                    'Check logs for additional error details'
                ]
            },
            'failed': {
                'title': 'General Task Failure Troubleshooting', 
                'steps': [
                    'Verify the failed task configuration',
                    'Check required permissions and dependencies',
                    'Test the operation manually on target host',
                    'Review task parameters and variables'
                ]
            },
            'unreachable': {
                'title': 'Host Unreachable Troubleshooting',
                'steps': [
                    'Test network connectivity: ping target_host',
                    'Verify SSH configuration and keys',
                    'Check firewall rules and port accessibility',
                    'Confirm target host is running and accessible'
                ]
            }
        }
        
        # Find matching fallback solution
        for error_pattern, solution_data in fallback_solutions.items():
            if error_pattern in error_type:
                return [{
                    'title': solution_data['title'],
                    'confidence': 0.5,
                    'steps': solution_data['steps'],
                    'category': 'fallback',
                    'type': 'fallback_solution',
                    'source': 'built_in_fallback',
                    'estimated_fix_time': '15-30 minutes'
                }]
        
        # Generic fallback
        return [{
            'title': 'General Error Analysis Steps',
            'confidence': 0.4,
            'steps': [
                'Carefully read the complete error message',
                'Check system logs and Ansible verbose output',
                'Verify system requirements and dependencies',
                'Test components individually to isolate the issue',
                'Consult official documentation for the specific error'
            ],
            'category': 'general',
            'type': 'generic_fallback',
            'source': 'built_in_fallback',
            'estimated_fix_time': '20-45 minutes'
        }]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get LLM generation statistics."""
        avg_response_time = (
            self.stats['total_response_time'] / self.stats['successful_requests']
            if self.stats['successful_requests'] > 0 else 0
        )
        
        return {
            'is_available': self.is_available,
            'model_name': self.model_name,
            'solutions_generated': self.stats['solutions_generated'],
            'successful_requests': self.stats['successful_requests'],
            'failed_requests': self.stats['failed_requests'],
            'timeouts': self.stats['timeouts'],
            'average_response_time': round(avg_response_time, 2),
            'total_requests': self.stats['successful_requests'] + self.stats['failed_requests'] + self.stats['timeouts']
        }
    
    def test_generation(self, test_error: str) -> Dict[str, Any]:
        """Test solution generation for a given error (for debugging)."""
        test_result = {
            'file_path': 'test',
            'line_number': 1,
            'confidence': 0.9,
            'error_type': 'test_error',
            'original_line': test_error,
            'context_before': ['Test context before error'],
            'context_after': ['Test context after error']
        }
        
        solutions = self.generate_solutions(test_result)
        
        return {
            'error_line': test_error,
            'solutions_found': len(solutions),
            'solutions': solutions,
            'statistics': self.get_statistics()
        } 