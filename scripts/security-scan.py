#!/usr/bin/env python3
"""Security scanning script for local development.

Usage:
    python scripts/security-scan.py [core|proxy]
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command and return exit code and output.

    Args:
        cmd: Command to run as list.
        cwd: Working directory.

    Returns:
        Tuple of (exit_code, output).
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout + result.stderr
    except Exception as e:
        return 1, str(e)


def check_dependency_scanning(package: str) -> int:
    """Run dependency vulnerability scanning.

    Args:
        package: Package name (core or proxy).

    Returns:
        Exit code (0 if no high/critical vulnerabilities).
    """
    print(f"\n{'='*60}")
    print(f"Running dependency vulnerability scan for {package}")
    print(f"{'='*60}")

    package_dir = PROJECT_ROOT / "packages" / package

    # Check if pip-audit is installed
    exit_code, _ = run_command(["pip-audit", "--version"])
    if exit_code != 0:
        print("Installing pip-audit...")
        run_command([sys.executable, "-m", "pip", "install", "pip-audit"])

    # Export dependencies
    print("\nExporting dependencies...")
    exit_code, output = run_command(
        ["poetry", "export", "--format", "requirements.txt", "--output", "requirements.txt", "--without-hashes"],
        cwd=package_dir,
    )
    if exit_code != 0:
        # Try alternative export format
        exit_code, output = run_command(
            ["poetry", "export", "--output", "requirements.txt", "--without-hashes"],
            cwd=package_dir,
        )

    requirements_file = package_dir / "requirements.txt"
    if not requirements_file.exists():
        print(f"Warning: Could not create requirements.txt for {package}")
        print("Skipping dependency scan.")
        return 0

    # Run pip-audit
    print("\nRunning pip-audit...")
    exit_code, output = run_command(
        ["pip-audit", "--requirement", "requirements.txt", "--format", "text"],
        cwd=package_dir,
    )

    if exit_code != 0:
        print(output)
        # Check for critical or high severity
        exit_code_json, output_json = run_command(
            ["pip-audit", "--requirement", "requirements.txt", "--format", "json"],
            cwd=package_dir,
        )
        if "CRITICAL" in output_json or "HIGH" in output_json:
            print("\n❌ High or critical vulnerabilities found!")
            return 1
        else:
            print("\n⚠️  Medium/low severity vulnerabilities found (non-blocking)")
            return 0
    else:
        print("✅ No vulnerabilities found")
        return 0


def check_bandit_scanning(package: str) -> int:
    """Run Bandit static analysis.

    Args:
        package: Package name (core or proxy).

    Returns:
        Exit code (0 if no high severity issues).
    """
    print(f"\n{'='*60}")
    print(f"Running static analysis security scan (Bandit) for {package}")
    print(f"{'='*60}")

    package_dir = PROJECT_ROOT / "packages" / package

    # Check if bandit is installed
    exit_code, _ = run_command(["bandit", "--version"])
    if exit_code != 0:
        print("Installing bandit...")
        run_command([sys.executable, "-m", "pip", "install", "bandit[toml]"])

    # Find apikeyrouter directories
    apikeyrouter_dirs = list(package_dir.glob("apikeyrouter*"))
    if not apikeyrouter_dirs:
        print(f"Warning: No apikeyrouter* directories found in {package_dir}")
        return 0

    # Run Bandit
    print("\nRunning Bandit...")
    exit_code, output = run_command(
        ["bandit", "-r"] + [str(d) for d in apikeyrouter_dirs] + ["-f", "txt"],
        cwd=package_dir,
    )

    print(output)

    if exit_code != 0:
        # Check for high severity
        exit_code_ll, output_ll = run_command(
            ["bandit", "-r"] + [str(d) for d in apikeyrouter_dirs] + ["-ll"],
            cwd=package_dir,
        )
        if "Severity: High" in output_ll:
            print("\n❌ High severity security issues found!")
            return 1
        else:
            print("\n⚠️  Medium/low severity issues found (non-blocking)")
            return 0
    else:
        print("✅ No security issues found")
        return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 if all scans pass).
    """
    package = sys.argv[1] if len(sys.argv) > 1 else "core"

    if package not in ["core", "proxy"]:
        print(f"Error: Invalid package '{package}'. Must be 'core' or 'proxy'")
        return 1

    print(f"Security scanning for package: {package}")

    # Run dependency scanning
    dep_exit_code = check_dependency_scanning(package)

    # Run Bandit scanning
    bandit_exit_code = check_bandit_scanning(package)

    # Summary
    print(f"\n{'='*60}")
    print("Security Scan Summary")
    print(f"{'='*60}")
    print(f"Dependency Scan: {'❌ Failed' if dep_exit_code != 0 else '✅ Passed'}")
    print(f"Bandit Scan: {'❌ Failed' if bandit_exit_code != 0 else '✅ Passed'}")

    if dep_exit_code != 0 or bandit_exit_code != 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


