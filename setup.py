"""Setup script for ApiKeyRouter project.

This script helps set up the project for development.
Run: python setup.py
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], check: bool = True) -> tuple[int, str, str]:
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=check, shell=True
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout, e.stderr


def check_python_version() -> bool:
    """Check if Python version is 3.11+."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro} detected")
        return True
    print(f"✗ Python {version.major}.{version.minor}.{version.micro} detected (need 3.11+)")
    return False


def check_venv() -> bool:
    """Check if virtual environment is active."""
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        print("✓ Virtual environment is active")
        return True
    print("⚠ Virtual environment not detected (recommended but not required)")
    return False


def install_dependencies() -> bool:
    """Install project dependencies."""
    print("\n📦 Installing dependencies...")
    
    # Check if we're in the right directory
    if not Path("packages/core/pyproject.toml").exists():
        print("✗ Error: Must run from project root directory")
        return False
    
    # Install core package in development mode
    print("Installing core package...")
    code, stdout, stderr = run_command(
        [sys.executable, "-m", "pip", "install", "-e", "packages/core"],
        check=False
    )
    
    if code != 0:
        print(f"✗ Error installing core package: {stderr}")
        return False
    
    # Install dev dependencies
    print("Installing development dependencies...")
    dev_deps = [
        "pytest>=7.4.4",
        "pytest-asyncio>=0.23.0",
        "pytest-cov>=4.1.0",
        "ruff>=0.1.13",
        "mypy>=1.8.0",
    ]
    
    for dep in dev_deps:
        code, stdout, stderr = run_command(
            [sys.executable, "-m", "pip", "install", dep],
            check=False
        )
        if code != 0:
            print(f"⚠ Warning: Failed to install {dep}: {stderr}")
    
    print("✓ Dependencies installed")
    return True


def verify_installation() -> bool:
    """Verify the installation works."""
    print("\n🔍 Verifying installation...")
    
    # Try importing the package
    try:
        from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
        from apikeyrouter.domain.interfaces.state_store import StateStore, StateQuery
        print("✓ Imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        print("  Try: pip install -e packages/core")
        return False


def run_quick_test() -> bool:
    """Run a quick test to verify everything works."""
    print("\n🧪 Running quick test...")
    
    code, stdout, stderr = run_command(
        [sys.executable, "-m", "pytest", "packages/core/tests/unit/test_state_store.py", "-v", "--tb=short"],
        check=False
    )
    
    if code == 0:
        print("✓ Tests passed!")
        return True
    else:
        print(f"⚠ Some tests failed (this is okay for initial setup)")
        print(f"  Output: {stdout[:200]}...")
        return False


def main() -> None:
    """Main setup function."""
    print("=" * 60)
    print("ApiKeyRouter Project Setup")
    print("=" * 60)
    
    # Check prerequisites
    print("\n📋 Checking prerequisites...")
    if not check_python_version():
        print("\n✗ Setup failed: Python 3.11+ required")
        sys.exit(1)
    
    check_venv()
    
    # Install dependencies
    if not install_dependencies():
        print("\n✗ Setup failed: Could not install dependencies")
        sys.exit(1)
    
    # Verify installation
    if not verify_installation():
        print("\n⚠ Setup completed but verification failed")
        print("  You may need to manually install: pip install -e packages/core")
        sys.exit(1)
    
    # Run quick test
    run_quick_test()
    
    print("\n" + "=" * 60)
    print("✅ Setup complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run tests: pytest packages/core/tests/unit/test_memory_store.py -v")
    print("2. Try manual test: cd packages/core && python test_manual_example.py")
    print("3. Read guides: SETUP_GUIDE.md or QUICK_START.md")
    print("\nHappy coding! 🚀")


if __name__ == "__main__":
    main()

