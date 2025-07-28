> [!NOTE]
> This project was developed with assistance from AI tools.

Python tool for analyzing log files with ML-enhanced error detection, clustering, and professional reporting.

## Quick Setup

```bash
pip install -r requirements.txt
python -m src.main --input test_logs/ --detector pattern --output analysis_report.html
python serve_results.py --format html
```

```bash
# Basic analysis
python -m src.main --input logs/ --output results.json

# With similarity error clustering  
python -m src.main --input logs/ --detector hybrid --enable-clustering --output analysis_report.html


## Key Components

### Detectors (`src/detectors/`)
- **`pattern.py`** - Fast regex/keyword matching (production-ready)
- **`semantic.py`** - NLP-based similarity detection 
- **`hybrid.py`** - Combines pattern + semantic + ML features
- **`statistical.py`** - Anomaly detection for durations, frequencies

### Configuration (`config/patterns.yaml`)
```yaml
# Add new error patterns
ansible_patterns:
  your_new_category:
    - "your pattern here"
    - "another.*regex.*pattern"

# Add semantic phrases  
semantic_phrases:
  your_category:
    - "natural language error description"
    
# Exclude false positives
false_positives:
  exclude_patterns:
    - "Success.*completed"  # Won't flag as error
```

### Processing (`src/processors/`)
- **`stream.py`** - File processing + multiprocessing
- **`context.py`** - Context extraction around errors
- **`clusterer.py`** - ML-based error grouping

## Development Workflow

### Testing New Patterns
```bash
# Test against your log files
python -m src.main --input your_logs/ --detector pattern --verbose

# Check what patterns matched
python serve_results.py --format cli --no-context
```

### Testing New Detectors
```bash
# Create detector in src/detectors/your_detector.py
# Follow pattern.py structure with detect() method
# Register in src/main.py create_detector()

# Test it
python -m src.main --detector your_detector --input test_logs/
```

### Performance Testing
```bash
# Pattern detector (fastest)
python -m src.main --detector pattern --input large_logs/ --parallel 8

# Semantic (slowest, most accurate)  
python -m src.main --detector semantic --input small_logs/ --parallel 1

# Hybrid (balanced)
python -m src.main --detector hybrid --input logs/ --enable-clustering
```

## File Structure

```
src/
├── detectors/        # Add new detection methods here
├── processors/       # File processing logic
├── models/          # Data structures (DetectionResult, etc.)
└── main.py          # CLI entry point

config/patterns.yaml  # Pattern definitions - edit this frequently
serve_results.py     # Results viewer - multiple output formats
requirements.txt     # Dependencies
test_logs/          # Sample data for testing
```

## Common Tasks

### Add New Error Pattern
1. Edit `config/patterns.yaml`
2. Add to appropriate category or create new one
3. Test: `python -m src.main --input test_logs/ --detector pattern`

### Modify Confidence Scoring
1. Adjust `pattern_weights` in `patterns.yaml`
2. Or modify `confidence_threshold`: `--confidence-threshold 0.8`

### Debug Detection Issues  
```bash
# Verbose output shows what patterns matched
python -m src.main --input problem_log.log --verbose --show-details

# Check clustering results
python show_clustering_results.py  # After running with --enable-clustering
```

### Handle New Log Format
1. Add patterns to `config/patterns.yaml`
2. Test with sample files
3. Adjust context windows if needed: `--context-before 10 --context-after 20`

## Output Analysis

Results include clustering info, retry grouping, and workflow analysis. Key fields:
- `cluster_id` - Groups similar errors together  
- `retry_count` - Grouped retry attempts
- `match_details` - What patterns/phrases caused detection

Use `serve_results.py` for easy result browsing - it handles all the clustering visualization automatically.

## Troubleshooting

- **Slow semantic processing**: Use `--detector pattern` or `--parallel 1`
- **Memory issues**: Process smaller batches, reduce parallel workers
- **Missing patterns**: Check `config/patterns.yaml`, add verbose logging
- **False positives**: Add exclusions to `false_positives` section 