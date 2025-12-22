# Release vX.Y.Z

**Release Date:** YYYY-MM-DD

## Summary

Brief overview of this release (2-3 sentences).

## What's Changed

### ✨ Added
- New feature 1
- New feature 2

### 🔄 Changed
- Improvement 1
- Improvement 2

### 🐛 Fixed
- Bug fix 1
- Bug fix 2

### 🗑️ Removed
- Removed feature 1 (if applicable)

### 🔒 Security
- Security fix 1 (if applicable)

## Breaking Changes

> ⚠️ **This release contains breaking changes. Please read the migration guide before upgrading.**

- Breaking change 1
- Breaking change 2

See [Migration Guide](docs/guides/migration-vX.Y.md) for details.

## Upgrade Instructions

### From Previous Version

```bash
# Update packages
pip install --upgrade apikeyrouter-core apikeyrouter-proxy

# Or with Poetry
poetry update apikeyrouter-core apikeyrouter-proxy
```

### Docker Users

```bash
# Pull latest image
docker pull <username>/apikeyrouter-proxy:vX.Y.Z

# Or use latest tag
docker pull <username>/apikeyrouter-proxy:latest
```

### Configuration Changes

If this release includes configuration changes:

1. Review [Configuration Guide](docs/guides/configuration.md)
2. Update your `.env` file if needed
3. Restart services

## Contributors

Thank you to all contributors who made this release possible:

- @contributor1
- @contributor2

## Full Changelog

For the complete list of changes, see [CHANGELOG.md](CHANGELOG.md).

**Full Changelog:** https://github.com/your-username/ApiKeyRouter/compare/vX.Y.Z...vX.Y.Z

## Installation

### PyPI

```bash
pip install apikeyrouter-core==X.Y.Z
pip install apikeyrouter-proxy==X.Y.Z
```

### Poetry

```bash
poetry add apikeyrouter-core==X.Y.Z
poetry add apikeyrouter-proxy==X.Y.Z
```

### Docker

```bash
docker pull <username>/apikeyrouter-proxy:vX.Y.Z
```

## Documentation

- [API Reference](packages/core/API_REFERENCE.md)
- [User Guide](docs/guides/user-guide.md)
- [Quick Start](docs/guides/quick-start.md)

## Support

- **Issues:** [GitHub Issues](https://github.com/your-username/ApiKeyRouter/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-username/ApiKeyRouter/discussions)
- **Security:** [SECURITY.md](SECURITY.md)

---

**Note:** Replace placeholders (X.Y.Z, YYYY-MM-DD, etc.) with actual values when creating the release.

