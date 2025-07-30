# 4 DETECTION METHODS: Step-by-Step Flows

## 1. 📝 PATTERN DETECTION (Fast & Reliable)
**What it does:** Matches exact text patterns and regex rules

**Step-by-step flow:**
```
Input: "fatal: [host]: UNREACHABLE! => {\"changed\": false...}"
  ↓
Step 1: Check if line contains trigger words ("fatal", "error", "failed")
Step 2: Run regex patterns against the line
Step 3: Find match: "fatal:" pattern + "UNREACHABLE!" pattern  
Step 4: Look up confidence weight from config (0.95 for fatal patterns)
Step 5: Create result with matched patterns list
  ↓
Output: DetectionResult(confidence=0.95, error_type="fatal", matched_patterns=["fatal:", "UNREACHABLE!"])
```

**Strength:** Instant results, 100% reliable for known patterns

## 2. 🧠 SEMANTIC DETECTION (Context Understanding)
**What it does:** Understands meaning using AI language models

**Step-by-step flow:**
```
Input: "fatal: [host]: UNREACHABLE! => {\"changed\": false...}"
  ↓
Step 1: Convert log line into numerical embeddings (vector representation)
Step 2: Compare against pre-computed error phrase embeddings 
Step 3: Calculate similarity scores (cosine similarity)
Step 4: Find closest match: "connection could not be established" (0.82 similarity)
Step 5: Apply confidence threshold and create result
  ↓
Output: DetectionResult(confidence=0.82, error_type="semantic_connection_error", matched_phrases=["connection failure"])
```

**Strength:** Understands variations in wording, context-aware

## 3. 🤖 ZERO-SHOT CLASSIFICATION (New Error Types)
**What it does:** Classifies errors without specific training using transformers

**Step-by-step flow:**
```
Input: "fatal: [host]: UNREACHABLE! => {\"changed\": false...}"
  ↓
Step 1: Load pre-trained transformer model (BERT-based)
Step 2: Define error categories: ["network_error", "auth_error", "system_error", "normal"]
Step 3: Model calculates probability for each category
Step 4: Select highest probability: "network_error" (0.73 confidence)
Step 5: Create result with classification details
  ↓
Output: DetectionResult(confidence=0.73, error_type="zeroshot_network_error", classification="network_error")
```

**Strength:** Handles completely new error types, no training needed

## 4. 📊 STATISTICAL ANOMALY DETECTION (Performance Issues)
**What it does:** Finds unusual patterns in timing, frequency, or content

**Step-by-step flow:**
```
Input: "fatal: [host]: UNREACHABLE! => {\"changed\": false...}"
  ↓
Step 1: Extract numerical features (line length, word count, timing if available)
Step 2: Compare against baseline statistics from previous lines
Step 3: Calculate Z-score: (current_value - mean) / standard_deviation
Step 4: Check if Z-score > threshold (default: 3.0 = 3 standard deviations)
Step 5: If anomalous, create result with statistical details
  ↓
Output: DetectionResult(confidence=0.45, error_type="statistical_anomaly", z_score=2.1) OR None if normal
```

**Strength:** Catches performance degradation, unusual patterns

## 🔄 HYBRID COMBINATION FLOW
**How all 4 methods combine:**

```
Input: Single log line
  ↓
Step 1: Run all 4 detectors in parallel
         Pattern → 0.95 confidence ✅
         Semantic → 0.82 confidence ✅  
         Zero-shot → 0.73 confidence ✅
         Statistical → 0.45 confidence ✅
  ↓
Step 2: Apply weighting system
         (0.95 × 0.4) + (0.82 × 0.3) + (0.73 × 0.2) + (0.45 × 0.1) = 0.82
  ↓
Step 3: Check if combined confidence > threshold (0.7)
Step 4: Merge all detection details into single result
  ↓
Output: DetectionResult(confidence=0.82, error_type="hybrid_fatal", all_matched_details)
```
