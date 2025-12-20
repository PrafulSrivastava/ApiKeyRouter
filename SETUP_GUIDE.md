# Project Setup Guide

This guide will help you set up the ApiKeyRouter project for development.

## Prerequisites

Before setting up the project, ensure you have the following installed:

### Required

1. **Python 3.11+**
   ```bash
   python --version  # Should show 3.11 or higher
   ```
   - Download from [python.org](https://www.python.org/downloads/)
   - Or use [pyenv](https://github.com/pyenv/pyenv) for version management

2. **Poetry 1.7.1+** (Package Manager)
   ```bash
   poetry --version  # Should show 1.7.1 or higher
   ```
   - Installation: Follow [Poetry installation guide](https://python-poetry.org/docs/#installation)
   - Windows: `(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -`
   - Or: `pip install poetry`

### Optional (for local development)

3. **Docker & Docker Compose** (for MongoDB/Redis)
   ```bash
   docker --version
   docker-compose --version
   ```
   - Download [Docker Desktop](https://www.docker.com/products/docker-desktop)

## Step-by-Step Setup

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd ApiKeyRouter
```

### Step 2: Install Poetry (if not already installed)

**Windows (PowerShell):**
```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

**macOS/Linux:**
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

**Add Poetry to PATH:**
- Windows: Add `%APPDATA%\Python\Scripts` to your PATH
- macOS/Linux: Add `~/.local/bin` to your PATH

**Verify installation:**
```bash
poetry --version
```

### Step 3: Install Project Dependencies

From the project root directory:

```bash
# Install all dependencies for workspace packages
poetry install
```

This will:
- Create a virtual environment (if not using system Python)
- Install dependencies for both `packages/core` and `packages/proxy`
- Install development dependencies (pytest, ruff, mypy, etc.)

**Note:** If you see warnings about Python version, ensure you have Python 3.11+ installed.

### Step 4: Verify Installation

```bash
# Activate Poetry shell (optional, but recommended)
poetry shell

# Verify Python version
python --version  # Should be 3.11+

# Verify packages are installed
poetry show

# Run a quick test
poetry run pytest packages/core/tests/unit/test_state_store.py -v
```

### Step 5: Set Up Environment Variables (Optional)

The project works in-memory by default, but you can configure optional services:

```bash
# Create .env file (if .env.example exists)
cp .env.example .env

# Edit .env with your configuration
# For now, you can skip this - the library works without it
```

### Step 6: Start Optional Services (Optional)

If you want to test with MongoDB/Redis:

```bash
# Start MongoDB (and optionally Redis)
docker-compose up -d

# Verify services are running
docker-compose ps

# View logs
docker-compose logs -f

# Stop services when done
docker-compose down
```

**Note:** The library works perfectly fine without these services - they're only needed for testing persistent backends.

## Verify Setup

### Run Tests

```bash
# Run all tests
poetry run pytest

# Run tests for core package
poetry run pytest packages/core/tests

# Run specific test file
poetry run pytest packages/core/tests/unit/test_memory_store.py -v
```

### Run Manual Test Script

```bash
cd packages/core
poetry run python test_manual_example.py
```

### Check Code Quality

```bash
# Format code
poetry run ruff format .

# Lint code
poetry run ruff check .

# Type check
poetry run mypy packages/core packages/proxy
```

## Common Setup Issues

### Issue 1: Poetry not found

**Solution:**
- Add Poetry to your PATH
- Or use `python -m poetry` instead of `poetry`
- Or reinstall Poetry

### Issue 2: Python version mismatch

**Error:** `The current project's supported Python version (>=3.11.0,<4.0.0) is not compatible with some of the required packages`

**Solution:**
```bash
# Check Python version
python --version

# If not 3.11+, install Python 3.11+
# Then configure Poetry to use it
poetry env use python3.11
```

### Issue 3: Dependency resolution fails

**Solution:**
```bash
# Update Poetry
poetry self update

# Clear cache and retry
poetry cache clear pypi --all
poetry install
```

### Issue 4: Import errors when running tests

**Error:** `ModuleNotFoundError: No module named 'apikeyrouter'`

**Solution:**
```bash
# Make sure you're in the project root
cd ApiKeyRouter

# Install in development mode
poetry install

# Or install core package specifically
cd packages/core
poetry install
```

### Issue 5: Windows PowerShell execution policy

**Error:** `cannot be loaded because running scripts is disabled on this system`

**Solution:**
```powershell
# Run as Administrator
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Development Workflow

### Working with Poetry Workspace

```bash
# Install all dependencies
poetry install

# Add dependency to core package
poetry add <package> --directory packages/core

# Add dependency to proxy package
poetry add <package> --directory packages/proxy

# Add dev dependency
poetry add --group dev <package>

# Run command in specific package
poetry run pytest --directory packages/core
```

### Using Poetry Shell

```bash
# Activate Poetry shell (recommended)
poetry shell

# Now you can run commands directly
pytest packages/core/tests -v
python test_manual_example.py

# Exit shell
exit
```

### Without Poetry Shell

```bash
# Prefix commands with 'poetry run'
poetry run pytest packages/core/tests -v
poetry run python packages/core/test_manual_example.py
```

## Project Structure

```
ApiKeyRouter/
├── packages/
│   ├── core/                    # Core library
│   │   ├── apikeyrouter/        # Source code
│   │   ├── tests/               # Tests
│   │   └── pyproject.toml       # Package config
│   └── proxy/                   # Proxy service (future)
│       └── pyproject.toml
├── docs/                        # Documentation
├── pyproject.toml               # Root workspace config
├── poetry.lock                  # Lock file (auto-generated)
└── docker-compose.yml           # Optional services
```

## Next Steps

After setup is complete:

1. ✅ **Run tests** to verify everything works:
   ```bash
   poetry run pytest packages/core/tests/unit/test_memory_store.py -v
   ```

2. ✅ **Try the manual test script**:
   ```bash
   cd packages/core
   poetry run python test_manual_example.py
   ```

3. ✅ **Read the testing guide**:
   ```bash
   cat packages/core/TESTING_GUIDE.md
   ```

4. ✅ **Explore the code**:
   - Core library: `packages/core/apikeyrouter/`
   - Tests: `packages/core/tests/`
   - Documentation: `docs/`

## Quick Reference

```bash
# Setup
poetry install                    # Install dependencies
poetry shell                      # Activate shell

# Testing
poetry run pytest                 # Run all tests
poetry run pytest -v              # Verbose output
poetry run pytest -k "test_name"  # Run specific test

# Code Quality
poetry run ruff format .          # Format code
poetry run ruff check .           # Lint code
poetry run mypy packages/core     # Type check

# Development
poetry add <package>              # Add dependency
poetry update                     # Update dependencies
poetry show                       # Show installed packages
```

## Getting Help

- **Documentation**: See `docs/` directory
- **Architecture**: `docs/architecture/`
- **Examples**: `docs/examples/`
- **Testing Guide**: `packages/core/TESTING_GUIDE.md`

## Troubleshooting

If you encounter issues:

1. Check Python version: `python --version` (must be 3.11+)
2. Check Poetry version: `poetry --version` (must be 1.7.1+)
3. Try clearing cache: `poetry cache clear pypi --all`
4. Reinstall: `poetry install --no-cache`
5. Check for error messages in the output

For more help, check the main README.md file.

