# Security Policy

## Supported Versions

We actively support security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability, please follow these steps:

1. **Do NOT** open a public GitHub issue
2. Email security concerns to: [security@example.com] (replace with actual security contact)
3. Include the following information:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **Critical vulnerabilities**: We aim to respond within 24 hours and patch within 7 days
- **High severity**: We aim to respond within 48 hours and patch within 14 days
- **Medium/Low severity**: We aim to respond within 1 week and patch in the next release cycle

### Security Updates

Security updates are automatically applied via Dependabot. Critical and high severity vulnerabilities are prioritized for immediate patching.

## Security Practices

### Dependency Management

- **Dependency Scanning**: Automated scanning with `pip-audit` runs on every commit and daily
- **Dependabot**: Automated dependency updates for security patches
- **Update Policy**:
  - Security updates: Immediate (auto-merged if tests pass)
  - Minor updates: Weekly review
  - Major updates: Manual review (breaking changes)

### Security Testing

- **Static Analysis**: Bandit scans code for security issues on every commit
- **Secret Scanning**: Automated secret scanning prevents accidental secret commits
- **Dependency Audits**: Regular dependency vulnerability scanning
- **CI Integration**: All security scans run automatically in CI/CD pipeline

### Security Headers

The proxy service includes security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (HTTPS only)

### Authentication & Authorization

- Management API requires `X-API-Key` header
- API keys are encrypted at rest
- Key material never exposed in logs, errors, or API responses
- Rate limiting enforced on management API (100 requests/minute per IP)

### Encryption

- API key material encrypted using AES-256 (Fernet)
- Encryption key from environment variable (never hardcoded)
- Keys decrypted only when needed for API calls
- No plaintext keys in memory longer than necessary

### Input Validation

- All inputs validated at API boundaries
- Injection attack prevention (SQL, NoSQL, command, script injection)
- Request validation using Pydantic models
- Clear validation error messages

### Audit Logging

- All key operations logged (registration, revocation, state changes)
- Key access events logged (decryption events)
- Audit trail excludes sensitive data (key material)
- Logs include key_id, timestamp, operation type, result

## Security Checklist

When contributing code, ensure:

- [ ] No hardcoded secrets or API keys
- [ ] No sensitive data in logs or error messages
- [ ] Input validation on all user inputs
- [ ] Proper error handling (no information leakage)
- [ ] Security headers included in responses
- [ ] Dependencies are up-to-date and secure
- [ ] No SQL injection vulnerabilities
- [ ] No command injection vulnerabilities
- [ ] Authentication/authorization properly implemented
- [ ] Rate limiting applied where appropriate

## Security Tools

The project uses the following security tools:

- **pip-audit**: Dependency vulnerability scanning
- **Bandit**: Static analysis for Python security issues
- **Dependabot**: Automated dependency updates
- **GitHub Secret Scanning**: Prevents secret commits
- **Gitleaks**: Additional secret scanning in CI

## Security Updates

Security updates are handled automatically:

1. **Dependabot** creates pull requests for security updates
2. **CI** runs tests and security scans
3. **Auto-merge** if tests pass (for security updates only)
4. **Manual review** for breaking changes

## Vulnerability Disclosure

We follow responsible disclosure practices:

1. Report vulnerabilities privately
2. We will acknowledge receipt within 48 hours
3. We will provide regular updates on remediation progress
4. We will credit security researchers (with permission) in release notes

## Security Contact

For security concerns, please contact: [security@example.com]

**Note**: Replace `[security@example.com]` with your actual security contact email.

