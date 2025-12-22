# Release Process Guide

This guide documents the complete release process for ApiKeyRouter, ensuring consistent and reliable releases.

## Table of Contents

- [Version Numbering Scheme](#version-numbering-scheme)
- [Release Checklist](#release-checklist)
- [Changelog Generation](#changelog-generation)
- [PyPI Publishing](#pypi-publishing)
- [Release Notes](#release-notes)
- [Automated Release Workflow](#automated-release-workflow)

## Version Numbering Scheme

### Semantic Versioning

ApiKeyRouter follows [Semantic Versioning 2.0.0](https://semver.org/) (SemVer) with the format:

```
MAJOR.MINOR.PATCH
```

### Version Components

**MAJOR** (X.0.0):
- Incremented for incompatible API changes
- Breaking changes that require code modifications
- Removal of deprecated features
- Major architectural changes

**Examples:**
- `1.0.0` → `2.0.0`: Complete API redesign
- `1.0.0` → `2.0.0`: Removed deprecated methods

**MINOR** (0.X.0):
- Incremented for backward-compatible functionality additions
- New features that don't break existing code
- New API endpoints or methods
- Deprecation notices (functionality still works)

**Examples:**
- `1.0.0` → `1.1.0`: Added new routing strategy
- `1.0.0` → `1.1.0`: Added support for new provider

**PATCH** (0.0.X):
- Incremented for backward-compatible bug fixes
- Security patches
- Performance improvements
- Documentation updates (if significant)

**Examples:**
- `1.0.0` → `1.0.1`: Fixed routing bug
- `1.0.0` → `1.0.1`: Security vulnerability fix

### Pre-Release Versions

For pre-release versions, append identifiers:

**Alpha** (0.1.0-alpha.1):
- Early development versions
- May contain incomplete features
- Not recommended for production

**Beta** (0.1.0-beta.1):
- Feature-complete but may contain bugs
- Suitable for testing
- API may change before release

**Release Candidate** (0.1.0-rc.1):
- Potentially final version
- Should be stable
- Only critical bug fixes expected

**Examples:**
- `0.1.0-alpha.1`: First alpha release
- `0.1.0-beta.2`: Second beta release
- `0.1.0-rc.1`: First release candidate
- `0.1.0`: Final release

### Version Bump Rules

**When to bump MAJOR:**
- Breaking API changes
- Removing public APIs
- Changing behavior in ways that break existing code
- Major architectural changes

**When to bump MINOR:**
- Adding new features
- Adding new API endpoints
- Adding new configuration options
- Deprecating features (but keeping them functional)

**When to bump PATCH:**
- Bug fixes
- Security patches
- Performance improvements
- Documentation fixes (minor)

### Version Examples

```
0.1.0          # Initial release
0.1.1          # Bug fix
0.2.0          # New feature added
0.2.1          # Bug fix
1.0.0          # First stable release
1.0.1          # Security patch
1.1.0          # New feature (backward compatible)
2.0.0          # Breaking changes
2.0.0-alpha.1  # Pre-release
2.0.0-beta.1   # Beta release
2.0.0-rc.1     # Release candidate
2.0.0          # Final release
```

## Release Checklist

### Pre-Release Steps

#### 1. Code Freeze
- [ ] All features for this release are merged
- [ ] No new features accepted (only bug fixes)
- [ ] Create release branch: `release/vX.Y.Z`

#### 2. Testing
- [ ] All unit tests pass: `poetry run pytest`
- [ ] All integration tests pass
- [ ] Performance benchmarks pass (no regressions)
- [ ] Manual testing completed
- [ ] Test on multiple Python versions (3.11+)
- [ ] Test on multiple operating systems (if applicable)

#### 3. Code Quality
- [ ] Linting passes: `poetry run ruff check .`
- [ ] Code formatted: `poetry run ruff format .`
- [ ] Type checking passes: `poetry run mypy packages/core packages/proxy`
- [ ] Security scan passes: `poetry run bandit -r packages/`
- [ ] No known vulnerabilities

#### 4. Documentation Updates
- [ ] README.md is up-to-date
- [ ] API documentation is current
- [ ] User guides are updated
- [ ] Migration guides created (if breaking changes)
- [ ] Examples are working and documented

#### 5. Changelog
- [ ] CHANGELOG.md updated with all changes
- [ ] Changes categorized (Added, Changed, Fixed, Removed, Security)
- [ ] Breaking changes clearly marked
- [ ] Migration notes included (if applicable)

#### 6. Version Bumping
- [ ] Update version in `packages/core/pyproject.toml`
- [ ] Update version in `packages/proxy/pyproject.toml`
- [ ] Update version in `__init__.py` files (if applicable)
- [ ] Verify version consistency across all files

### Release Steps

#### 7. Release Branch
- [ ] Create release branch: `git checkout -b release/vX.Y.Z`
- [ ] Final testing on release branch
- [ ] All checks pass

#### 8. Tagging
- [ ] Create annotated tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
- [ ] Tag format: `vX.Y.Z` (e.g., `v1.0.0`)
- [ ] Push tag: `git push origin vX.Y.Z`

#### 9. GitHub Release
- [ ] Create GitHub Release from tag
- [ ] Use release notes template
- [ ] Attach release assets (if any)
- [ ] Mark as "Latest release" (if applicable)

#### 10. PyPI Publishing
- [ ] Build packages: `poetry build`
- [ ] Test on Test PyPI first
- [ ] Publish to PyPI: `poetry publish`
- [ ] Verify packages on PyPI

### Post-Release Steps

#### 11. Merge Back
- [ ] Merge release branch to `main`
- [ ] Merge release branch to `develop` (if using)

#### 12. Announcement
- [ ] Update project website (if applicable)
- [ ] Announce on social media
- [ ] Notify stakeholders
- [ ] Update documentation sites

#### 13. Monitoring
- [ ] Monitor for issues
- [ ] Respond to bug reports promptly
- [ ] Prepare hotfix if critical issues found

## Changelog Generation

### Changelog Format

The CHANGELOG.md follows the [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New feature X
- New API endpoint Y

### Changed
- Improved performance of Z

### Fixed
- Bug fix A
- Bug fix B

### Removed
- Deprecated feature C

### Security
- Security fix D

## [1.0.0] - 2025-01-15

### Added
- Initial release
- Core routing functionality
- FastAPI proxy service
```

### Changelog Categories

**Added:**
- New features
- New APIs
- New configuration options
- New dependencies

**Changed:**
- Changes in existing functionality
- Performance improvements
- API modifications (backward compatible)

**Deprecated:**
- Features that will be removed in future versions
- APIs that are no longer recommended

**Removed:**
- Removed features
- Removed APIs

**Fixed:**
- Bug fixes
- Error corrections

**Security:**
- Security vulnerability fixes

### Changelog Template

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- 

### Changed
- 

### Deprecated
- 

### Removed
- 

### Fixed
- 

### Security
- 
```

### Manual vs Automated Changelog

**Manual Changelog:**
- Maintained by developers during development
- Updated in PRs
- Reviewed during release process
- More control and context

**Automated Changelog:**
- Generated from commit messages
- Uses conventional commits
- Can be automated in CI/CD
- Less context, more consistent format

**Recommendation:** Use manual changelog for better context and clarity.

### Changelog Examples

**Minor Release:**
```markdown
## [1.1.0] - 2025-01-20

### Added
- Support for Anthropic Claude API
- New cost optimization routing strategy
- Health check endpoint in proxy service

### Changed
- Improved routing decision performance by 30%
- Updated documentation with new examples

### Fixed
- Fixed issue where keys could get stuck in Throttled state
- Fixed memory leak in quota tracking
```

**Patch Release:**
```markdown
## [1.0.1] - 2025-01-18

### Fixed
- Fixed authentication middleware not validating API keys correctly
- Fixed CORS headers not being applied to all endpoints

### Security
- Updated cryptography dependency to address CVE-2024-XXXXX
```

**Major Release:**
```markdown
## [2.0.0] - 2025-02-01

### Added
- New async API for better performance
- Support for custom routing strategies

### Changed
- **BREAKING:** Router API now uses async/await pattern
- **BREAKING:** KeyManager methods now return coroutines
- Improved error handling with custom exception types

### Removed
- **BREAKING:** Removed synchronous API (use async API instead)
- **BREAKING:** Removed deprecated `route_sync()` method

### Migration
See [MIGRATION.md](docs/guides/migration-v2.md) for migration guide.
```

## PyPI Publishing

### Package Preparation

#### 1. Update Version
```bash
# Update version in pyproject.toml
# packages/core/pyproject.toml
version = "1.0.0"

# packages/proxy/pyproject.toml
version = "1.0.0"
```

#### 2. Update Metadata
- [ ] Description is current
- [ ] Authors are correct
- [ ] License is specified
- [ ] Keywords are relevant
- [ ] Classifiers are appropriate

#### 3. Build Configuration
Ensure `pyproject.toml` includes:
```toml
[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

### PyPI Account Setup

#### 1. Create PyPI Account
- [ ] Create account on [PyPI](https://pypi.org/)
- [ ] Verify email address
- [ ] Enable two-factor authentication (recommended)

#### 2. Create API Token
- [ ] Go to Account Settings → API tokens
- [ ] Create new token with appropriate scope
- [ ] Save token securely (use password manager)

#### 3. Configure Poetry
```bash
# Configure Poetry with PyPI token
poetry config pypi-token.pypi your-api-token-here

# Or use environment variable
export POETRY_PYPI_TOKEN_PYPI=your-api-token-here
```

### Build Process

#### 1. Clean Previous Builds
```bash
# Remove old build artifacts
rm -rf dist/
rm -rf *.egg-info/
```

#### 2. Build Packages
```bash
# Build core package
cd packages/core
poetry build

# Build proxy package
cd ../proxy
poetry build
```

#### 3. Verify Builds
```bash
# Check built packages
ls -la dist/

# Should see:
# - apikeyrouter-core-X.Y.Z-py3-none-any.whl
# - apikeyrouter-core-X.Y.Z.tar.gz
# - apikeyrouter-proxy-X.Y.Z-py3-none-any.whl
# - apikeyrouter-proxy-X.Y.Z.tar.gz
```

### Test PyPI Usage

**Always test on Test PyPI first:**

#### 1. Create Test PyPI Account
- [ ] Create account on [Test PyPI](https://test.pypi.org/)
- [ ] Create API token

#### 2. Configure Test PyPI
```bash
poetry config repositories.testpypi https://test.pypi.org/legacy/
poetry config pypi-token.testpypi your-test-token-here
```

#### 3. Publish to Test PyPI
```bash
cd packages/core
poetry publish --repository testpypi

cd ../proxy
poetry publish --repository testpypi
```

#### 4. Test Installation
```bash
# Create test virtual environment
python -m venv test-env
source test-env/bin/activate  # On Windows: test-env\Scripts\activate

# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ apikeyrouter-core
pip install --index-url https://test.pypi.org/simple/ apikeyrouter-proxy

# Test import
python -c "from apikeyrouter import ApiKeyRouter; print('Success!')"
```

### Publishing to PyPI

#### 1. Final Verification
- [ ] All tests pass
- [ ] Version numbers are correct
- [ ] Packages build successfully
- [ ] Tested on Test PyPI

#### 2. Publish Core Package
```bash
cd packages/core
poetry publish
```

#### 3. Publish Proxy Package
```bash
cd packages/proxy
poetry publish
```

#### 4. Verify on PyPI
- [ ] Check package pages on PyPI
- [ ] Verify version numbers
- [ ] Test installation: `pip install apikeyrouter-core apikeyrouter-proxy`

### Version Management

**Important:** PyPI does not allow re-uploading the same version. If you need to fix a release:

1. **Patch Release:** Bump patch version (e.g., `1.0.0` → `1.0.1`)
2. **Yanked Release:** Mark version as yanked (use `poetry publish --remove` or PyPI web interface)

**Yanking a Release:**
```bash
# Remove/yank a version (use with caution)
poetry publish --remove
```

## Release Notes

Release notes are created from the changelog and published with each GitHub release. See [Release Notes Template](.github/RELEASE_NOTES_TEMPLATE.md) for the template.

### Release Notes Structure

1. **Version and Date**
2. **Summary** (brief overview)
3. **What's Changed** (from changelog)
4. **Migration Notes** (if breaking changes)
5. **Upgrade Instructions**
6. **Full Changelog** (link)

## Automated Release Workflow

### GitHub Actions Release Workflow

A GitHub Actions workflow can automate parts of the release process:

1. **Trigger:** Create release tag
2. **Build:** Build packages
3. **Test:** Run tests
4. **Publish:** Publish to PyPI
5. **Create Release:** Create GitHub release

See `.github/workflows/release.yml` (if created) for automation details.

### Manual Release Process

For now, releases are manual. Follow the checklist above for each release.

## Release Schedule

**No fixed schedule** - releases are made when:
- Significant features are complete
- Critical bugs are fixed
- Security vulnerabilities are patched
- Enough changes accumulate for a release

**Recommendation:** Aim for regular releases (monthly or quarterly) to keep the project active and users engaged.

## Emergency Releases

For critical security fixes:

1. Create hotfix branch from latest release tag
2. Apply fix
3. Bump patch version
4. Test thoroughly
5. Release immediately
6. Merge back to main/develop

## Additional Resources

- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Poetry Publishing](https://python-poetry.org/docs/cli/#publish)
- [PyPI Help](https://pypi.org/help/)

