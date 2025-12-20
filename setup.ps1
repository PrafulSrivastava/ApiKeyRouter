# ApiKeyRouter Setup Script for Windows PowerShell
# Run: .\setup.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ApiKeyRouter Project Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Check Python version
Write-Host "`n[1/5] Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "Python 3\.(1[1-9]|[2-9]\d)") {
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
    exit 1
}

# Check if venv exists
Write-Host "`n[2/5] Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✓ Virtual environment found" -ForegroundColor Green
    Write-Host "  Activate with: venv\Scripts\Activate.ps1" -ForegroundColor Gray
} else {
    Write-Host "⚠ No virtual environment found" -ForegroundColor Yellow
    $create = Read-Host "  Create one? (y/n)"
    if ($create -eq "y") {
        python -m venv venv
        Write-Host "✓ Virtual environment created" -ForegroundColor Green
    }
}

# Install core package
Write-Host "`n[3/5] Installing core package..." -ForegroundColor Yellow
python -m pip install -e packages/core
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Core package installed" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to install core package" -ForegroundColor Red
    exit 1
}

# Install dev dependencies
Write-Host "`n[4/5] Installing development dependencies..." -ForegroundColor Yellow
$devDeps = @("pytest>=7.4.4", "pytest-asyncio>=0.23.0", "pytest-cov>=4.1.0", "ruff>=0.1.13", "mypy>=1.8.0")
foreach ($dep in $devDeps) {
    python -m pip install $dep --quiet
}
Write-Host "✓ Development dependencies installed" -ForegroundColor Green

# Verify installation
Write-Host "`n[5/5] Verifying installation..." -ForegroundColor Yellow
python -c "from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore; print('✓ Import successful')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Installation verified" -ForegroundColor Green
} else {
    Write-Host "⚠ Import test failed" -ForegroundColor Yellow
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Activate venv: venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "2. Run tests: pytest packages/core/tests/unit/test_memory_store.py -v" -ForegroundColor White
Write-Host "3. Try manual test: cd packages/core && python test_manual_example.py" -ForegroundColor White
Write-Host "`nHappy coding! 🚀" -ForegroundColor Cyan

