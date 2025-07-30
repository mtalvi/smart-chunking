#!/usr/bin/env python3
"""
Test Llama 3.1 integration with smart-chunking results
Run this after: ollama serve & ollama pull llama3.1:8b-instruct-q4_0
"""

import json
import requests
import sys

def test_ollama_connection():
    """Test if Ollama is running and accessible"""
    try:
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"✅ Ollama is running with {len(models)} models")
            for model in models:
                print(f"   - {model['name']}")
            return True
        else:
            print("❌ Ollama is not responding")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama. Is it running? (ollama serve)")
        print("💡 Run: ollama serve")
        return False

def test_natural_language_parsing():
    """Test natural language to JSON alert rule conversion"""
    
    print("\n�� TESTING: Natural Language Alert Creation")
    
    user_request = "Alert me when any playbook shows SSH UNREACHABLE errors on critical hosts"
    
    prompt = f"""Convert this natural language request to a JSON alert rule:
"{user_request}"

Available error types: fatal, failed, unreachable, error
Available detectors: pattern, semantic, hybrid

Return only valid JSON in this format:
{{
    "rule_id": "generated_rule",
    "detector_config": {{
        "type": "hybrid",
        "confidence_threshold": 0.8
    }},
    "conditions": {{
        "error_types": ["relevant_types"],
        "frequency": {{"threshold": 1, "window": "10m"}}
    }},
    "notifications": {{
        "channels": ["slack"],
        "severity": "high"
    }}
}}"""

    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3.1:8b-instruct-q4_0",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096
            }
        })
        
        if response.status_code == 200:
            result = response.json()["response"]
            print("✅ Llama 3.1 Response:")
            print(result[:300] + "..." if len(result) > 300 else result)
            
            # Try to parse as JSON
            try:
                json_start = result.find('{')
                json_end = result.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = result[json_start:json_end]
                    parsed = json.loads(json_str)
                    print("✅ Successfully parsed JSON!")
                    return True
            except:
                print("⚠️  JSON parsing needs refinement")
                
        else:
            print(f"❌ API Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return False

def test_rca_generation():
    """Test RCA generation using smart-chunking context"""
    
    print("\n🔍 TESTING: RCA Generation with Smart-Chunking Context")
    
    # Simulate your actual smart-chunking detection result
    detection_result = {
        "error_type": "hybrid_fatal",
        "confidence": 0.95,
        "file_path": "test_logs/job_1434747.txt",
        "line_number": 374,
        "original_line": "fatal: [bastion.sqght.internal]: UNREACHABLE! => SSH authentication failed",
        "matched_patterns": ["fatal:", "UNREACHABLE!"],
        "context_before": ["TASK [Check SSH connectivity]", "Connecting to bastion host..."],
        "context_after": ["NO MORE HOSTS LEFT", "Playbook execution terminated"],
        "timestamp": "2025-07-18T20:45:46Z"
    }
    
    prompt = f"""Generate a professional Root Cause Analysis report for this Ansible failure:

INCIDENT DETAILS:
- Error Type: {detection_result['error_type']}
- Confidence: {detection_result['confidence']*100:.1f}% (Smart-chunking detection)
- Location: {detection_result['file_path']}:{detection_result['line_number']}
- Patterns Matched: {detection_result['matched_patterns']}

ERROR LINE:
{detection_result['original_line']}

CONTEXT:
Before: {' | '.join(detection_result['context_before'])}
After: {' | '.join(detection_result['context_after'])}

TIMESTAMP: {detection_result['timestamp']}

Generate a professional incident report with:
1. Incident Summary
2. Timeline Analysis
3. Root Cause Analysis  
4. Impact Assessment
5. Recommended Actions

Keep it concise but thorough."""

    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3.1:8b-instruct-q4_0",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096
            }
        })
        
        if response.status_code == 200:
            result = response.json()["response"]
            print("✅ Llama 3.1 RCA Report:")
            print(result[:500] + "..." if len(result) > 500 else result)
            return True
        else:
            print(f"❌ API Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return False

def test_solution_suggestions():
    """Test solution suggestions for Ansible errors"""
    
    print("\n💡 TESTING: Solution Suggestions")
    
    prompt = """Generate specific troubleshooting steps for this Ansible SSH authentication error:

ERROR: fatal: [bastion.sqght.internal]: UNREACHABLE! => SSH key authentication failed
PATTERN CONFIDENCE: 95% (detected by smart-chunking system)
CONTEXT: Connection to bastion host during infrastructure deployment

Provide step-by-step troubleshooting guide with:
1. Immediate checks to perform
2. Common causes and solutions
3. Verification steps
4. Prevention measures

Focus on Ansible-specific solutions."""

    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3.1:8b-instruct-q4_0", 
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 4096
            }
        })
        
        if response.status_code == 200:
            result = response.json()["response"]
            print("✅ Llama 3.1 Solution Guide:")
            print(result[:400] + "..." if len(result) > 400 else result)
            return True
        else:
            print(f"❌ API Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return False

def main():
    """Run all Llama 3.1 integration tests"""
    
    print("🦙 LLAMA 3.1 + SMART-CHUNKING INTEGRATION TEST")
    print("=" * 60)
    
    # Test connection first
    if not test_ollama_connection():
        print("\n💡 Setup Instructions:")
        print("1. Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh")
        print("2. Start server: ollama serve")
        print("3. Pull model: ollama pull llama3.1:8b-instruct-q4_0")
        sys.exit(1)
    
    # Run integration tests
    tests_passed = 0
    total_tests = 3
    
    if test_natural_language_parsing():
        tests_passed += 1
        
    if test_rca_generation():
        tests_passed += 1
        
    if test_solution_suggestions():
        tests_passed += 1
    
    print(f"\n🎯 TEST RESULTS: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("✅ SUCCESS: Llama 3.1 integration is working!")
        print("\n🚀 NEXT STEPS:")
        print("1. Integrate with your smart-chunking detection pipeline")
        print("2. Add structured JSON parsing for alert rules")
        print("3. Create web UI for natural language input")
        print("4. Deploy with your existing system")
    else:
        print("⚠️  Some tests failed. Check Ollama setup and model availability.")

if __name__ == "__main__":
    main()
