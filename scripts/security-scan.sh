#!/bin/bash
# Security scanning script for local development

set -e

PACKAGE=${1:-"core"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT/packages/$PACKAGE"

echo "Running security scans for package: $PACKAGE"
echo "=========================================="

# Check if pip-audit is installed
if ! command -v pip-audit &> /dev/null; then
    echo "Installing pip-audit..."
    pip install pip-audit
fi

# Check if bandit is installed
if ! command -v bandit &> /dev/null; then
    echo "Installing bandit..."
    pip install bandit[toml]
fi

# Export dependencies
echo ""
echo "Exporting dependencies..."
poetry export --format requirements.txt --output requirements.txt --without-hashes 2>/dev/null || \
poetry export --output requirements.txt --without-hashes 2>/dev/null || \
echo "Warning: Could not export dependencies. Install poetry-plugin-export if needed."

# Run pip-audit
echo ""
echo "Running dependency vulnerability scan (pip-audit)..."
if [ -f requirements.txt ]; then
    pip-audit --requirement requirements.txt --format text || echo "Vulnerabilities found. Review output above."
else
    echo "Warning: requirements.txt not found. Skipping dependency scan."
fi

# Run Bandit
echo ""
echo "Running static analysis security scan (Bandit)..."
bandit -r apikeyrouter* -f txt || echo "Security issues found. Review output above."

echo ""
echo "Security scan complete!"

