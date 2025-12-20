# Quick Start Guide

Get up and running with ApiKeyRouter in 5 minutes!

## Prerequisites Check

```bash
# Check Python version (need 3.11+)
python --version

# Check if Poetry is installed
poetry --version
```

## Setup Options

### Option 1: Using Poetry (Recommended)

If you have Poetry installed:

```bash
# 1. Install dependencies
poetry install

# 2. Activate shell
poetry shell

# 3. Run tests to verify
poetry run pytest packages/core/tests/unit/test_memory_store.py -v
```

### Option 2: Using pip + venv (Alternative)

If you don't have Poetry:

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate virtual environment
# Windows PowerShell:
venv\Scripts\Activate.ps1
# Windows CMD:
venv\Scripts\activate.bat
# macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -e packages/core
pip install pytest pytest-asyncio ruff mypy

# 4. Run tests
pytest packages/core/tests/unit/test_memory_store.py -v
```

### Option 3: Using Existing venv

If you already have a venv:

```bash
# 1. Activate existing venv
venv\Scripts\Activate.ps1  # Windows PowerShell

# 2. Install dependencies
pip install -e packages/core
pip install pytest pytest-asyncio

# 3. Run tests
cd packages/core
pytest tests/unit/test_memory_store.py -v
```

## Verify Installation

### Quick Test

```bash
cd packages/core
python test_manual_example.py
```

You should see:
```
============================================================
InMemoryStateStore Manual Testing
============================================================
...
✓ All manual tests passed!
```

### Run Unit Tests

```bash
# From project root
pytest packages/core/tests/unit/test_memory_store.py -v

# Or from packages/core
cd packages/core
pytest tests/unit/test_memory_store.py -v
```

## What's Installed

After setup, you'll have:

- ✅ **InMemoryStateStore** - Complete state store implementation
- ✅ **StateStore Interface** - Abstract interface for state persistence
- ✅ **All Models** - APIKey, QuotaState, RoutingDecision, StateTransition
- ✅ **Query Interface** - Flexible state querying
- ✅ **63 Tests** - Comprehensive test coverage

## Next Steps

1. **Read the Testing Guide**: `packages/core/TESTING_GUIDE.md`
2. **Try Examples**: `docs/examples/comprehensive-usage-example.py`
3. **Explore Code**: `packages/core/apikeyrouter/`

## Troubleshooting

**Import errors?**
```bash
# Make sure you're in the right directory
cd packages/core

# Install in development mode
pip install -e .
```

**Tests not found?**
```bash
# Run from project root
pytest packages/core/tests/unit/test_memory_store.py -v
```

**Python version error?**
```bash
# Check version
python --version  # Must be 3.11+

# If wrong version, use pyenv or install Python 3.11+
```

For detailed setup instructions, see `SETUP_GUIDE.md`.

