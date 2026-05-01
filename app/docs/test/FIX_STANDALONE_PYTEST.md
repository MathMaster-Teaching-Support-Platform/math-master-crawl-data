# Fix: Standalone Tests vs Pytest Isolation

## Problem

The standalone test scripts (`tests/test_phase1.py` and `tests/test_phase2.py`) had function names starting with `test_`, which caused pytest to try to run them as test functions, leading to fixture errors:

```
ERROR at setup of test_image_encoding - fixture 'service' not found
ERROR at setup of test_json_parsing - fixture 'service' not found  
ERROR at setup of test_rate_limiter - fixture 'service' not found
```

## Solution

Renamed all test functions in standalone scripts from `test_*` to `run_*`:

### Phase 1 (test_phase1.py)
- `test_pdf_parser()` → `run_phase1_tests()`

### Phase 2 (test_phase2.py)
- `test_service_initialization()` → `run_service_initialization()`
- `test_image_encoding()` → `run_image_encoding()`
- `test_json_parsing()` → `run_json_parsing()`
- `test_rate_limiter()` → `run_rate_limiter()`
- `test_content_block()` → `run_content_block()`
- `test_page_analysis()` → `run_page_analysis()`

## Result

Now these scripts work correctly in both modes:

### ✅ Standalone Mode (No pytest)
```bash
python tests/test_phase1.py    # Works - runs run_phase1_tests()
python tests/test_phase2.py    # Works - runs all run_*() functions
```

### ✅ Pytest Mode
```bash
pytest tests/ -v               # Works - ignores run_*() functions
pytest tests/test_phase1.py    # Works - no collected tests
pytest tests/test_phase2.py    # Works - no collected tests
```

## Why This Matters

- **Standalone tests**: Direct Python execution, no pytest needed
- **Pytest integration**: Ability to run comprehensive test suite without conflicts
- **Clear separation**: Non-test files can coexist with test discovery

## Files Modified

1. `tests/test_phase1.py` - Line 68: renamed main function
2. `tests/test_phase2.py` - Lines 58, 94, 134, 233, 263, 311: renamed functions  
3. `tests/test_phase2.py` - Line 354: updated function call in main()

## Testing After Fix

```bash
# Verify standalone tests work
python tests/test_phase1.py    # Should display "ALL TESTS PASSED!"
python tests/test_phase2.py    # Should display "ALL TESTS PASSED!"

# Verify pytest doesn't conflict
pytest tests/ -v               # Should show 0 collected tests
pytest tests/ --collect-only   # Should show no tests from test_phase*.py
```

## Pattern for Future Phases

When creating Phase 3+ tests:
- Use `run_*()` for standalone test functions, not `test_*()`
- This allows pytest to safely import and use standalone scripts
- Maintain single file for both standalone and pytest support
