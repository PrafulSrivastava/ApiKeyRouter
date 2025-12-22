# Contributing to ApiKeyRouter

Thank you for your interest in contributing to ApiKeyRouter! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

### Prerequisites

- Python 3.11+
- Poetry 1.7.1+
- Git
- Docker & Docker Compose (optional, for local MongoDB/Redis)

### Setting Up Development Environment

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/your-username/ApiKeyRouter.git
   cd ApiKeyRouter
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Start local services (optional):**
   ```bash
   docker-compose up -d
   ```

5. **Run tests to verify setup:**
   ```bash
   poetry run pytest
   ```

## Development Workflow

### Branch Strategy

- **main**: Production-ready code
- **develop**: Integration branch for features
- **feature/***: Feature branches (e.g., `feature/add-new-provider`)
- **bugfix/***: Bug fix branches (e.g., `bugfix/fix-routing-issue`)
- **hotfix/***: Critical production fixes

### Creating a Branch

```bash
# Create and switch to a new feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b bugfix/your-bug-fix-name
```

### Making Changes

1. **Make your changes** following the coding standards
2. **Write or update tests** for your changes
3. **Run tests locally** to ensure everything passes
4. **Update documentation** if needed
5. **Commit your changes** with clear commit messages

### Commit Message Guidelines

We follow conventional commit message format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(routing): add cost-based routing strategy

Implement cost optimization algorithm that selects keys
based on estimated request cost while maintaining reliability.

Closes #123
```

```
fix(key-manager): handle edge case in state transitions

Fix issue where key state transitions could fail silently
when quota limits are reached.

Fixes #456
```

## Coding Standards

### General Principles

- **Follow PEP 8** with project-specific modifications (100 character line length)
- **Use type hints** for all public APIs
- **Write clear, self-documenting code**
- **Keep functions focused** and single-purpose
- **Follow SOLID principles**

### Code Style

The project uses **ruff** for formatting and linting:

```bash
# Format code
poetry run ruff format .

# Lint code
poetry run ruff check .

# Type check
poetry run mypy packages/core packages/proxy
```

**Key Standards:**
- **Line Length:** 100 characters (not 80)
- **Formatter:** ruff (format on save recommended)
- **Type Checking:** mypy with strict mode enabled
- **Import Sorting:** Automatic via ruff

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `ApiKeyRouter`, `QuotaAwarenessEngine` |
| Functions/Methods | snake_case | `route_request`, `get_eligible_keys` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_ATTEMPTS`, `DEFAULT_TIMEOUT` |
| Private Methods | `_leading_underscore` | `_calculate_score`, `_validate_state` |
| Type Variables | PascalCase | `T`, `KeyType`, `ProviderType` |

### Critical Rules

1. **Never Log API Key Material**: API keys must NEVER appear in logs, error messages, or exceptions
2. **All State Transitions Must Be Explicit**: Use KeyManager/QuotaAwarenessEngine, never direct assignment
3. **Provider-Specific Logic Only in Adapters**: Core domain logic must never branch on provider identity
4. **All Async I/O Must Use Async/Await**: No blocking I/O operations
5. **Routing Decisions Must Be Explainable**: Every routing decision must include an explanation field

See [`docs/architecture/coding-standards.md`](docs/architecture/coding-standards.md) for complete coding standards.

## Testing Requirements

### Test Coverage

- **Minimum coverage:** 80% overall
- **Domain logic:** 90%+ coverage required
- **All new code must include tests**

### Writing Tests

**Test Organization:**
- Test files: `test_*.py` or `*_test.py`
- Test location: Mirror source structure in `tests/` directory
- Test naming: `test_<functionality>_<scenario>`

**Test Types:**
- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test component interactions
- **Benchmark tests**: Performance tests (marked with `@pytest.mark.benchmark`)

**Example:**
```python
import pytest
from apikeyrouter.domain.components.key_manager import KeyManager

@pytest.mark.asyncio
async def test_key_manager_register_key_success():
    """Test successful key registration."""
    manager = KeyManager()
    key_id = await manager.register_key("sk-test-key", "openai")
    assert key_id is not None
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run tests for specific package
poetry run pytest packages/core/tests

# Run with coverage
poetry run pytest --cov=packages/core/apikeyrouter --cov-report=html

# Run specific test types
poetry run pytest -m unit          # Unit tests only
poetry run pytest -m integration  # Integration tests only
poetry run pytest -m benchmark    # Benchmark tests only
```

### Test Requirements Before PR

- All tests must pass
- Coverage must not decrease
- New code must have tests
- Performance benchmarks must not regress

## Pull Request Process

### Before Submitting

1. **Ensure all tests pass:**
   ```bash
   poetry run pytest
   ```

2. **Run code quality checks:**
   ```bash
   poetry run ruff format .
   poetry run ruff check .
   poetry run mypy packages/core packages/proxy
   ```

3. **Update documentation** if your changes affect:
   - API behavior
   - Configuration options
   - Installation process
   - Usage examples

4. **Update CHANGELOG.md** with your changes (if applicable)

### Creating a Pull Request

1. **Push your branch:**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a Pull Request** on GitHub:
   - Use the PR template
   - Provide a clear title and description
   - Link related issues
   - Include screenshots/examples if applicable

3. **PR Checklist:**
   - [ ] Code follows coding standards
   - [ ] Tests added/updated and passing
   - [ ] Documentation updated
   - [ ] CHANGELOG.md updated (if applicable)
   - [ ] No breaking changes (or clearly documented)
   - [ ] CI checks passing

### PR Review Process

1. **Automated Checks:**
   - CI runs tests, linting, and type checking
   - Code coverage is checked
   - Security scans run automatically

2. **Code Review:**
   - At least one maintainer must approve
   - Address all review comments
   - Keep PR focused and reasonably sized

3. **Merge:**
   - PRs are merged via "Squash and Merge" or "Rebase and Merge"
   - Maintainers will handle merging after approval

## Issue Reporting

### Before Creating an Issue

1. **Search existing issues** to avoid duplicates
2. **Check documentation** to see if it's already covered
3. **Verify it's a bug** or valid feature request

### Bug Reports

Use the bug report template and include:

- **Clear description** of the bug
- **Steps to reproduce** the issue
- **Expected behavior** vs actual behavior
- **Environment details** (Python version, OS, etc.)
- **Error messages/logs** if applicable
- **Minimal reproduction case** if possible

### Feature Requests

Use the feature request template and include:

- **Clear description** of the feature
- **Use case** and motivation
- **Proposed solution** (if you have one)
- **Alternatives considered** (if any)

### Security Issues

**Do NOT report security vulnerabilities through public GitHub issues.**

See [SECURITY.md](SECURITY.md) for details on reporting security issues.

## Documentation

### Code Documentation

- **Docstrings:** Required for all public APIs (Google style)
- **Type hints:** Prefer type hints over docstring type annotations
- **Comments:** Explain "why", not "what"

**Example:**
```python
def route(
    self,
    request_intent: RequestIntent,
    objective: Optional[RoutingObjective] = None
) -> SystemResponse:
    """Route request intelligently across available keys.
    
    Args:
        request_intent: Request to route
        objective: Optional routing objective (cost, reliability, etc.)
        
    Returns:
        SystemResponse with completion and metadata
        
    Raises:
        NoEligibleKeysError: If no keys available for routing
        BudgetExceededError: If request would exceed budget
    """
```

### User Documentation

- Update README.md if installation/usage changes
- Update API documentation if APIs change
- Add examples for new features
- Update guides in `docs/guides/` if applicable

## Getting Help

- **Documentation:** Check [`docs/`](docs/) directory
- **Issues:** Search existing issues or create a new one
- **Discussions:** Use GitHub Discussions for questions

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md (if maintained)
- Release notes for significant contributions
- Project documentation

Thank you for contributing to ApiKeyRouter! 🎉

