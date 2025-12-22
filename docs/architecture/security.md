# Security

Security requirements are **MANDATORY** and directly impact code generation. The system must protect sensitive assets (API keys), enforce access control, and maintain full auditability for compliance.

## Input Validation

**Validation Library:** pydantic (built-in validation for all models)

**Validation Location:** API boundary (FastAPI request validation) and domain model construction

**Required Rules:**
- **All external inputs MUST be validated** - Request bodies, query parameters, path parameters
- **Validation at API boundary** - Before processing, not during
- **Whitelist approach preferred** - Explicit allow lists, not deny lists
- **Type validation** - Pydantic ensures type safety
- **Constraint validation** - Range checks, format validation (e.g., key ID format)

**Validation Examples:**
```python
# API Request Validation (Pydantic)
class KeyRegistrationRequest(BaseModel):
    key_material: str = Field(..., min_length=10, max_length=200)
    provider_id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    metadata: dict = Field(default_factory=dict)

# Domain Model Validation
class APIKey(BaseModel):
    id: str = Field(..., pattern=r"^key_[a-z0-9]+$")
    state: KeyState = Field(...)
    # Pydantic validates on construction
```

**Rejection Behavior:**
- Invalid inputs return 400 Bad Request immediately
- Error messages do not expose internal structure
- Validation errors logged (without sensitive data)

## Authentication & Authorization

**Auth Method:** API key authentication for management endpoints

**Session Management:** Stateless (no sessions, API key per request)

**Required Patterns:**
- **Management API:** Requires `X-API-Key` header
- **Routing API:** No authentication (proxy handles provider auth internally)
- **Key Material Access:** Never exposed via API (only key IDs)
- **Principle of Least Privilege:** Management API key has limited scope

**Authentication Flow:**
```python
# Management API Middleware
async def verify_management_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != settings.management_api_key:
        raise HTTPException(401, "Invalid management API key")
    return True
```

**Authorization Rules:**
- **Key Registration:** Requires management API key
- **Key Revocation:** Requires management API key
- **Policy Configuration:** Requires management API key
- **State Queries:** Requires management API key (sensitive data)
- **Routing Requests:** No auth required (public proxy)

**Fail-Safe Defaults:**
- **Missing API Key:** Deny access (401 Unauthorized)
- **Invalid API Key:** Deny access (401 Unauthorized)
- **Missing Configuration:** Deny all management operations (fail secure)

## Secrets Management

**Development:** `.env` file (git-ignored), environment variables

**Production:** Platform secrets management (Railway/Render secrets), future: Vault/AWS Secrets Manager

**Code Requirements:**
- **NEVER hardcode secrets** - All secrets via configuration
- **Access via configuration service only** - No direct environment variable access in business logic
- **No secrets in logs or error messages** - API keys never appear in logs
- **Encryption at rest** - Key material encrypted before storage
- **Encryption in transit** - HTTPS for all API communication

**Key Material Handling:**
```python
# Encryption at rest
from cryptography.fernet import Fernet

class KeyManager:
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)
    
    async def register_key(self, key_material: str, ...):
        # Encrypt before storage
        encrypted = self.cipher.encrypt(key_material.encode())
        # Store encrypted, never plaintext
        await self.state_store.save_key(encrypted, ...)
    
    async def get_key_material(self, key_id: str) -> str:
        # Decrypt only when needed for API call
        encrypted = await self.state_store.get_encrypted_key(key_id)
        return self.cipher.decrypt(encrypted).decode()
```

**Secret Rotation:**
- **API Keys:** Can be rotated without system restart
- **Encryption Keys:** Rotation requires re-encryption of all keys
- **Management API Key:** Rotated via environment variable update

**Secret Storage:**
- **In-Memory:** Decrypted keys in memory only (never persisted)
- **MongoDB:** Encrypted key material stored
- **Redis:** Encrypted key material (if used)
- **Environment Variables:** Management API key, encryption keys

## API Security

**Rate Limiting:**
- **Management API:** 100 requests/minute per IP
- **Routing API:** Per-key rate limits (provider-specific)
- **Implementation:** FastAPI rate limiting middleware
- **Error Response:** 429 Too Many Requests with `Retry-After` header

**CORS Policy:**
- **Development:** Allow localhost origins
- **Production:** Restrict to known origins (configurable)
- **Configuration:** Environment variable `CORS_ORIGINS`

**Security Headers:**
- **Required Headers:**
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000` (HTTPS only)
- **Implementation:** FastAPI middleware adds headers

**HTTPS Enforcement:**
- **Production:** HTTPS required (platform handles TLS termination)
- **Development:** HTTP allowed (localhost)
- **Redirect:** HTTP → HTTPS redirect in production

**Input Sanitization:**
- **Request Bodies:** Pydantic validation sanitizes input
- **Query Parameters:** Type conversion and validation
- **Path Parameters:** Pattern validation (no injection risks)
- **No SQL Injection Risk:** No raw SQL queries (MongoDB ODM)

## Data Protection

**Encryption at Rest:**
- **Key Material:** Encrypted using Fernet (symmetric encryption)
- **Encryption Key:** From environment variable or key management service
- **MongoDB:** Database-level encryption (if supported by provider)
- **Backups:** Encrypted backups (if backups are created)

**Encryption in Transit:**
- **HTTPS:** All API communication over TLS 1.2+
- **Provider APIs:** HTTPS required (no HTTP provider APIs)
- **Database:** TLS connection to MongoDB (if remote)
- **Redis:** TLS connection to Redis (if remote)

**PII Handling:**
- **No PII Collected:** System does not collect user-identifiable information
- **Request Content:** May contain PII (user messages), not stored by default
- **Logging Restrictions:** Request/response bodies not logged (may contain PII)
- **Audit Logs:** Only metadata logged (key IDs, timestamps, not content)

**Data Retention:**
- **Request Contexts:** 7 days (configurable)
- **Routing Decisions:** 30 days (configurable)
- **State Transitions:** 90 days (for audit compliance)
- **API Keys:** Permanent (until deleted)

**What NOT to Log:**
- API key material (even encrypted)
- Request/response bodies (may contain sensitive data)
- Full error stack traces in production (sanitized)
- Internal routing scores (too verbose, may leak logic)

## Dependency Security

**Scanning Tool:** Dependabot (GitHub) + manual review

**Update Policy:** 
- **Security Updates:** Immediate (automated via Dependabot)
- **Minor Updates:** Monthly review
- **Major Updates:** Quarterly review (breaking changes)

**Approval Process:**
- **New Dependencies:** Require justification and security review
- **Security Updates:** Auto-merge if tests pass
- **Breaking Changes:** Manual review required

**Vulnerability Response:**
- **Critical:** Patch within 24 hours
- **High:** Patch within 7 days
- **Medium/Low:** Patch in next release cycle

**Dependency Policies:**
- **Prefer Well-Maintained:** Active projects with security updates
- **Avoid Abandoned:** No dependencies without recent updates (>1 year)
- **Minimize Surface Area:** Only essential dependencies

## Security Testing

**SAST Tool:** Bandit (static analysis for Python)

**DAST Tool:** Not applicable (library, not web application)

**Penetration Testing:** Annual (or before major releases)

**Security Test Categories:**
1. **Secret Leakage:** Automated scan for hardcoded secrets
2. **Input Validation:** Fuzz testing for API endpoints
3. **Authentication:** Test unauthorized access attempts
4. **Encryption:** Verify key material encryption
5. **Audit Logging:** Verify all security events logged

**Security Test Examples:**
```python
def test_api_key_not_logged():
    """Verify API keys never appear in logs."""
    with log_capture() as logs:
        router.register_key("sk-secret-key", "openai")
        assert "sk-secret-key" not in str(logs)

def test_unauthorized_management_api_access():
    """Verify management API requires authentication."""
    response = client.post("/api/v1/keys", json={...})
    assert response.status_code == 401
```

## Security Compliance

**Audit Logging:**
- **All Key Operations:** Registration, revocation, state changes
- **All Policy Changes:** Creation, modification, deletion
- **All Budget Changes:** Creation, modification, enforcement
- **All Management API Access:** Authentication attempts, operations

**Audit Log Format:**
```json
{
  "timestamp": "2025-12-19T10:30:00Z",
  "event": "key_registered",
  "actor": "management_api",
  "resource": "key_abc123",
  "action": "register",
  "result": "success"
}
```

**Compliance Evidence:**
- **Audit Trails:** Complete history of all security-relevant operations
- **Policy Adherence:** All decisions traceable to policies
- **Access Logs:** All management API access logged
- **State Transitions:** All key state changes logged

**Security Incident Response:**
- **Detection:** Automated alerts for suspicious activity
- **Containment:** Immediate key revocation if compromised
- **Investigation:** Audit logs provide full traceability
- **Recovery:** Key rotation, policy updates, system hardening

## Security Best Practices

**Defense in Depth:**
- Multiple layers of security (encryption, authentication, validation)
- No single point of failure
- Fail-safe defaults at every layer

**Principle of Least Privilege:**
- Management API key has minimal required permissions
- Components access only what they need
- No unnecessary permissions

**Security by Design:**
- Security considered from architecture stage
- Not bolted on later
- Regular security reviews

**Regular Updates:**
- Dependencies updated regularly
- Security patches applied promptly
- Security testing continuous

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Checklist Results Report - will run architect checklist)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Security section.
