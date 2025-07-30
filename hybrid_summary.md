# HYBRID DETECTION: The Complete Picture

## 🎯 THE 4 DETECTION METHODS

The current weights are just the weights right now and will be modified based on training.

### 1. 📝 Pattern Detection (40% weight)
- **What**: Regex patterns and keyword matching
- **Strength**: Fast, reliable for known Ansible patterns
- **Example**: Finds "fatal:", "UNREACHABLE!", "FAILED - RETRYING"
- **Your benefit**: Immediate detection of standard Ansible failures

### 2. 🧠 Semantic Detection (30% weight)  
- **What**: NLP understanding using sentence embeddings
- **Strength**: Understands meaning and context
- **Example**: Knows "SSH connection refused" = connectivity problem
- **Your benefit**: Handles variations in wording, different verbosity levels

### 3. Zero-Shot Classification (20% weight)
- **What**: AI that can classify errors without specific training
- **Strength**: Handles completely new error types
- **Example**: New AWS service failures, infrastructure changes
- **Your benefit**: Adapts to your evolving infrastructure

### 4. 📊 Statistical Anomaly Detection (10% weight)
- **What**: Finds unusual patterns in log timing/frequency
- **Strength**: Catches performance degradation
- **Example**: Tasks taking 5x longer than normal
- **Your benefit**: Proactive performance monitoring

## 🔄 HOW THEY COMBINE

**Standard Mode (Default):**
- Any detector can trigger an alert
- Results weighted by importance (Pattern=40%, Semantic=30%, etc.)
- More comprehensive coverage

**Consensus Mode (--require-consensus):**
- Multiple detectors must agree
- More conservative, fewer false positives
- Higher confidence in results

## 💡 WHY HYBRID SOLVES "COMPLEX SCENARIOS"

The challenge: "Complex scenarios complicate accurate/complete detection"

**Hybrid solution:**
- ✅ **Multi-line errors**: Pattern finds trigger, Semantic understands context
- ✅ **Retry vs failure**: Multiple methods distinguish final failure
- ✅ **New error types**: Zero-shot adapts to infrastructure changes
- ✅ **Performance issues**: Statistical catches degradation
- ✅ **Variable verbosity**: Semantic adapts to -v/-vv/-vvv levels
- ✅ **False positives**: Multiple methods reduce noise
