# PII Analyzer Tests

This directory contains tests for the PII Analyzer functionality.

## Running Tests

### With pytest (Recommended)

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/test_file_discovery.py

# Run with coverage
pytest tests/ --cov=src
```

### With unittest

```bash
# Run all tests
python -m unittest discover tests

# Run a specific test
python -m unittest tests/test_file_discovery.py
```

### In Docker

```bash
docker compose -f docker-compose.prod.yml run --rm pii-analyzer pytest tests/
```

## Manual Testing

Some tests provide a manual testing mode for interactive exploration:

```bash
python tests/test_file_discovery.py --manual
```

This will create sample files and a database, then print information about what was created.

## Test Coverage

| Test File | Description |
|-----------|-------------|
| `test_analyzers.py` | Tests Presidio PII detection |
| `test_anonymizers.py` | Tests PII redaction |
| `test_cli.py` | Tests command-line interface |
| `test_extractors.py` | Tests text extraction (Tika, OCR) |
| `test_file_discovery.py` | Tests file scanning and registration |
| `test_worker_management.py` | Tests parallel processing |

## Sample Files

The `sample_files/` directory contains test files for various formats:

- `pdf_samples/` - Sample PDF files
- `text_samples/` - Sample text files

## Creating New Tests

When creating new tests:

1. Name the test file with the prefix `test_` (e.g., `test_new_feature.py`)
2. Use pytest or unittest framework
3. Create temporary files/directories that are cleaned up after the test
4. Include detailed docstrings explaining what is being tested
5. Test both success and failure cases
