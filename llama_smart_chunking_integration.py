#!/usr/bin/env python3
"""
Llama 3.1 Integration with Smart-Chunking System
Demonstrates how to add LLM capabilities to existing detection engine
"""

import json
import requests
import sys
import os
from typing import Dict, Any, Optional

# Add smart-chunking modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

class Llama31Client:
    """Simple client for local Llama 3.1 via Ollama"""
    
    def __init__(self, base_url="http://localhost:11434", model="llama3.1:8b-instruct-q4_0"):
        self.base_url = base_url
        self.model = model
        
    def generate(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.1) -> str:
        """Generate text using Llama 3.1"""
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 8192,  # Use full context window
                "temperature": temperature,
                "top_p": 0.9,
                "num_predict": max_tokens
            }
        }
        
        try:
            response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=60)
            
            if response.status_code == 200:
                return response.json()["response"]
            else:
                raise Exception(f"Llama API error: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to Ollama. Is it running? (ollama serve)")

class SmartChunkingLlamaEnhancer:
    """Enhances smart-chunking results with Llama 3.1 insights"""
    
    def __init__(self):
        self.llm = Llama31Client()
        
    def parse_natural_language_alert(self, user_input: str, available_patterns: Dict[str, Any]) -> Dict[str, Any]:
        """Convert natural language to alert rule using smart-chunking pattern knowledge"""
        
        prompt = f"""Convert this natural language alert request to JSON:
"{user_input}"

AVAILABLE ANSIBLE PATTERNS:
{list(available_patterns.get('ansible_errors', []))}

AVAILABLE ERROR TYPES:
{list(available_patterns.get('error_types', {}).keys())}

CONFIDENCE WEIGHTS:
{available_patterns.get('weights', {})}

Generate JSON in this exact format:
{{
    "rule_id": "generated_alert_rule",
    "detector_config": {{
        "type": "hybrid",
        "confidence_threshold": 0.8,
        "enable_clustering": true
    }},
    "conditions": {{
        "error_types": ["relevant_error_types_from_above"],
        "host_pattern": "extracted_from_request_or_*",
        "frequency": {{"threshold": NUMBER_FROM_REQUEST, "window": "TIME_FROM_REQUEST"}}
    }},
    "notifications": {{
        "channels": ["slack"],
        "severity": "critical_or_high_or_medium"
    }}
}}

Return ONLY the JSON, no explanations."""

        try:
            response = self.llm.generate(prompt, temperature=0.1)
            
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                # Fallback if JSON extraction fails
                return self._create_fallback_rule(user_input)
                
        except Exception as e:
            print(f"LLM parsing error: {e}")
            return self._create_fallback_rule(user_input)
    
    def generate_rca_report(self, detection_result: Dict[str, Any]) -> str:
        """Generate professional RCA using smart-chunking context"""
        
        prompt = f"""Generate a professional Root Cause Analysis report for this Ansible failure.

SMART-CHUNKING DETECTION RESULTS:
- Error Type: {detection_result.get('error_type', 'unknown')}
- Confidence: {detection_result.get('confidence', 0)*100:.1f}% (ML-based detection)
- Location: {detection_result.get('file_path', 'unknown')}:{detection_result.get('line_number', 0)}
- Patterns Matched: {detection_result.get('matched_patterns', [])}
- Semantic Analysis: {detection_result.get('matched_semantic_phrases', [])}

CONTEXT BEFORE ERROR:
{chr(10).join(detection_result.get('context_before', [])[-3:])}

ERROR LINE:
{detection_result.get('original_line', 'No line available')}

CONTEXT AFTER ERROR:
{chr(10).join(detection_result.get('context_after', [])[:3])}

ADDITIONAL CONTEXT:
- Timestamp: {detection_result.get('timestamp', 'Unknown')}
- Cluster ID: {detection_result.get('cluster_id', 'None')}
- Detector: {detection_result.get('detector_name', 'Unknown')}

Create a comprehensive incident report with these sections:
1. **Incident Summary** - Brief overview with key facts
2. **Timeline Analysis** - Sequence of events from context
3. **Root Cause Analysis** - Technical analysis using smart-chunking insights
4. **Impact Assessment** - Scope and business impact
5. **Recommended Actions** - Specific steps to resolve and prevent

Use the smart-chunking confidence score and pattern analysis to support your conclusions.
Write in professional incident report format."""

        try:
            return self.llm.generate(prompt, max_tokens=2000, temperature=0.2)
        except Exception as e:
            return f"Error generating RCA: {e}\n\nFallback: Manual analysis needed for error at {detection_result.get('file_path', 'unknown')}:{detection_result.get('line_number', 0)}"
    
    def suggest_solutions(self, detection_result: Dict[str, Any]) -> str:
        """Generate troubleshooting solutions using detection insights"""
        
        prompt = f"""Generate specific troubleshooting steps for this Ansible error.

SMART-CHUNKING ANALYSIS:
- Error Classification: {detection_result.get('error_type', 'unknown')}
- Detection Confidence: {detection_result.get('confidence', 0)*100:.1f}% (highly reliable)
- Matched Patterns: {detection_result.get('matched_patterns', [])}
- Semantic Understanding: {detection_result.get('matched_semantic_phrases', [])}

ERROR DETAILS:
{detection_result.get('original_line', 'No details available')[:200]}

CONTEXT CLUES:
{chr(10).join(detection_result.get('context_before', [])[-2:] + detection_result.get('context_after', [])[:2])}

Generate a practical troubleshooting guide with:

1. **Immediate Verification Steps** - Quick checks to confirm the issue
2. **Common Solutions** - Step-by-step resolution procedures  
3. **Advanced Troubleshooting** - If basic steps don't work
4. **Prevention Strategies** - How to avoid this in the future
5. **Related Issues** - What else to check

Focus on Ansible-specific commands and configurations. Use the smart-chunking pattern analysis to guide your recommendations."""

        try:
            return self.llm.generate(prompt, max_tokens=1500, temperature=0.3)
        except Exception as e:
            return f"Error generating solutions: {e}\n\nFallback: Check Ansible documentation for {detection_result.get('error_type', 'this error type')}"
    
    def _create_fallback_rule(self, user_input: str) -> Dict[str, Any]:
        """Create a basic alert rule if LLM parsing fails"""
        return {
            "rule_id": "fallback_rule",
            "detector_config": {
                "type": "hybrid",
                "confidence_threshold": 0.8
            },
            "conditions": {
                "error_types": ["error", "failed", "fatal"],
                "frequency": {"threshold": 1, "window": "10m"}
            },
            "notifications": {
                "channels": ["slack"],
                "severity": "medium"
            },
            "note": f"Fallback rule for: {user_input}"
        }

def demonstrate_integration():
    """Demonstrate Llama 3.1 enhancing smart-chunking results"""
    
    print("🦙 SMART-CHUNKING + LLAMA 3.1 INTEGRATION DEMO")
    print("=" * 60)
    
    # Initialize the enhancer
    enhancer = SmartChunkingLlamaEnhancer()
    
    # Simulate smart-chunking pattern knowledge
    smart_chunking_patterns = {
        "ansible_errors": ["fatal:", "UNREACHABLE!", "FAILED - RETRYING:", "failed:"],
        "error_types": {
            "hybrid_fatal": 0.95,
            "hybrid_failed": 0.80,
            "fatal": 0.95,
            "failed": 0.80,
            "unreachable": 0.95
        },
        "weights": {
            "fatal_patterns": 0.95,
            "failed_patterns": 0.80,
            "unreachable_patterns": 0.95
        }
    }
    
    # Simulate smart-chunking detection result (your actual data)
    detection_result = {
        "error_type": "hybrid_fatal",
        "confidence": 0.95,
        "file_path": "test_logs/job_1434747.txt",
        "line_number": 374,
        "original_line": "fatal: [bastion.sqght.internal]: UNREACHABLE! => {\"changed\": false, \"msg\": \"Failed to connect to the host via ssh: no such identity: ssh_provision_sqght: No such file or directory\"}",
        "detector_name": "HybridDetector",
        "matched_patterns": ["fatal:", "UNREACHABLE!"],
        "matched_semantic_phrases": ["connection failure", "ssh authentication"],
        "context_before": [
            "",
            "TASK [Check if k8s interpreter venv is installed] ******************************",
            "Friday 18 July 2025  20:45:46 +0000 (0:00:00.024)       0:00:37.441 ***********"
        ],
        "context_after": [
            "",
            "NO MORE HOSTS LEFT *************************************************************",
            ""
        ],
        "cluster_id": 1,
        "timestamp": "2025-07-18T20:45:46Z"
    }
    
    print("1️⃣  SMART-CHUNKING DETECTION (Your existing system)")
    print(f"✅ Detected: {detection_result['error_type']} (confidence: {detection_result['confidence']*100:.1f}%)")
    print(f"📍 Location: {detection_result['file_path']}:{detection_result['line_number']}")
    print(f"🎯 Patterns: {detection_result['matched_patterns']}")
    
    print("\n2️⃣  NATURAL LANGUAGE ALERT CREATION (New Llama 3.1 feature)")
    user_request = "Alert me if any playbook shows UNREACHABLE hosts on critical infrastructure"
    
    try:
        alert_rule = enhancer.parse_natural_language_alert(user_request, smart_chunking_patterns)
        print(f"🧠 User Request: '{user_request}'")
        print("✅ Generated Alert Rule:")
        print(json.dumps(alert_rule, indent=2))
    except Exception as e:
        print(f"❌ Alert parsing error: {e}")
    
    print("\n3️⃣  ROOT CAUSE ANALYSIS (New Llama 3.1 feature)")
    try:
        rca_report = enhancer.generate_rca_report(detection_result)
        print("📊 Generated RCA Report (first 300 chars):")
        print(rca_report[:300] + "...")
    except Exception as e:
        print(f"❌ RCA generation error: {e}")
    
    print("\n4️⃣  SOLUTION SUGGESTIONS (New Llama 3.1 feature)")
    try:
        solutions = enhancer.suggest_solutions(detection_result)
        print("💡 Generated Solutions (first 300 chars):")
        print(solutions[:300] + "...")
    except Exception as e:
        print(f"❌ Solution generation error: {e}")
    
    print("\n🎯 INTEGRATION BENEFITS:")
    print("✅ Your 95% accurate detection provides reliable LLM input")
    print("✅ Your 240+ patterns enhance LLM prompts with domain knowledge")
    print("✅ Your context extraction gives LLM rich analysis foundation")
    print("✅ Free Llama 3.1 = No API costs during development")
    print("✅ Local deployment = Privacy and control")
    
    print("\n🚀 NEXT STEPS:")
    print("1. Set up Ollama: curl -fsSL https://ollama.ai/install.sh | sh")
    print("2. Pull model: ollama pull llama3.1:8b-instruct-q4_0")
    print("3. Start server: ollama serve")
    print("4. Run this demo: python llama_smart_chunking_integration.py")

if __name__ == "__main__":
    demonstrate_integration()
