# Security Best Practices - LabLink

**Version:** 1.0.0
**Last Updated:** 2025-11-14
**Owner:** Security Team

---

## Table of Contents

1. [Dependency Management](#dependency-management)
2. [Secure Coding](#secure-coding)
3. [Authentication & Authorization](#authentication--authorization)
4. [Data Protection](#data-protection)
5. [API Security](#api-security)
6. [Secrets Management](#secrets-management)
7. [CI/CD Security](#cicd-security)
8. [Deployment Security](#deployment-security)
9. [Incident Response](#incident-response)

---

## Dependency Management

### Vulnerability Scanning

✅ **Automated Scanning (CI/CD)**
- pip-audit runs on every commit (blocking)
- safety check runs advisory scans
- bandit scans Python code for security issues
- Scans configured in `.github/workflows/comprehensive-tests.yml`

### Updating Dependencies

**Policy:** Review and update dependencies quarterly or when vulnerabilities are discovered.

**Process:**
```bash
# 1. Check for outdated packages
pip list --outdated

# 2. Audit for vulnerabilities
pip-audit --desc

# 3. Update specific package
# In requirements.txt: package==x.y.z → package>=x.y.z+1
pip install -r requirements.txt

# 4. Run full test suite
pytest tests/

# 5. Security scan
pip-audit --desc

# 6. Commit with security justification
git commit -m "security: Upgrade package to fix CVE-XXXX-YYYY"
```

### Acceptable Risk Documentation

When a vulnerability cannot be immediately fixed:
1. **Document** in `docs/security/` with CVE details
2. **Justify** why it's acceptable (e.g., dev-only, not used)
3. **Add** to CI ignore list with comment
4. **Review** quarterly to check if fix is available

**Example:**
```yaml
# In .github/workflows/comprehensive-tests.yml
pip-audit --ignore-vuln GHSA-xxxx-yyyy  # Dev only, documented in docs/security/
```

---

## Secure Coding

### Input Validation

✅ **Always validate and sanitize inputs**

```python
# Good: Using Pydantic for validation
from pydantic import BaseModel, validator, Field

class CommandRequest(BaseModel):
    equipment_id: str = Field(..., min_length=1, max_length=50)
    command: str = Field(..., min_length=1, max_length=1000)

    @validator('command')
    def validate_command(cls, v):
        # Prevent command injection
        dangerous = [';', '|', '&', '`', '$', '(', ')']
        if any(char in v for char in dangerous):
            raise ValueError("Command contains dangerous characters")
        return v
```

❌ **Never trust user input**
```python
# Bad: Direct string interpolation
command = f"echo {user_input}"  # Command injection risk!

# Good: Use parameterized commands or escape
import shlex
command = ['echo', shlex.quote(user_input)]
```

### SQL Injection Prevention

✅ **Use parameterized queries**
```python
# Good: Parameterized query
cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, hashed_password)
)

# Bad: String concatenation
cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")  # NEVER!
```

### Path Traversal Prevention

✅ **Validate file paths**
```python
from pathlib import Path

def safe_path(base_dir: Path, filename: str) -> Path:
    """Ensure path stays within base directory."""
    requested = (base_dir / filename).resolve()
    if not requested.is_relative_to(base_dir):
        raise ValueError("Path traversal attempt detected")
    return requested
```

### Secrets in Code

❌ **NEVER commit secrets**
```python
# Bad
API_KEY = "sk-1234567890abcdef"  # NEVER!

# Good
import os
API_KEY = os.getenv("LABLINK_API_KEY")
if not API_KEY:
    raise ValueError("API_KEY not configured")
```

---

## Authentication & Authorization

### Password Security

✅ **Use bcrypt for password hashing**
```python
from security.auth import hash_password, verify_password

# Hash password (automatically salted)
hashed = hash_password(plain_password)

# Verify password
if verify_password(plain_password, hashed):
    # Authenticated
    pass
```

**Requirements:**
- Minimum 12 characters
- Include uppercase, lowercase, number, special character
- Bcrypt work factor: 12 rounds
- Never log passwords (even hashed)

### JWT Tokens

✅ **Secure JWT configuration**
```python
# Token generation (server/security/auth.py)
- Short-lived access tokens (15 minutes)
- Longer-lived refresh tokens (7 days)
- Include minimal claims (sub, exp, iat)
- Sign with strong secret (256+ bits entropy)
- Validate exp, iat, nbf on every request
```

**Never:**
- Store sensitive data in JWT payload (it's base64, not encrypted)
- Use predictable secrets (use secrets.token_urlsafe(32))
- Skip signature verification
- Accept tokens without expiration

### Multi-Factor Authentication (MFA)

✅ **TOTP-based MFA available**
- Use `security/mfa.py` functions
- 6-digit codes, 30-second window
- Backup codes (one-time use, hashed)
- QR code generation for easy setup

**Implementation:**
```python
from security.mfa import generate_totp_secret, verify_totp_token

# Setup
secret = generate_totp_secret()
qr_uri = get_totp_qr_uri(secret, "user@example.com", "LabLink")

# Verification
if verify_totp_token(user_provided_token, secret):
    # MFA verified
    pass
```

### Role-Based Access Control (RBAC)

✅ **Principle of Least Privilege**
```python
from security.rbac import check_permission

# Check before action
if not check_permission(user, ResourceType.EQUIPMENT, PermissionAction.WRITE):
    raise PermissionError("Insufficient permissions")
```

**Roles:**
- **Admin:** Full system access
- **Operator:** Equipment operation, no config changes
- **Viewer:** Read-only access
- **Custom:** Define specific permission sets

---

## Data Protection

### Data at Rest

✅ **Sensitive data encryption**
- Use `cryptography` library for file encryption
- Encrypt database backup files
- Encrypt configuration files containing credentials
- Use OS keyring for local secret storage

```python
from cryptography.fernet import Fernet

# Generate key (store securely!)
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt
encrypted = cipher.encrypt(sensitive_data.encode())

# Decrypt
decrypted = cipher.decrypt(encrypted).decode()
```

### Data in Transit

✅ **TLS/HTTPS required**
- API server: HTTPS only in production
- WebSocket: WSS (WebSocket Secure) only
- Database connections: Use TLS if remote
- Equipment communication: Encrypt if supported

**Uvicorn TLS Configuration:**
```python
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8443,
    ssl_keyfile="/path/to/key.pem",
    ssl_certfile="/path/to/cert.pem",
    ssl_ca_certs="/path/to/ca.pem"  # Optional: Client cert validation
)
```

### PII Handling

✅ **Minimize PII collection**
- Collect only what's necessary
- Document why each PII field is needed
- Provide user data export (GDPR compliance)
- Implement data retention policies
- Log access to PII

❌ **Never:**
- Log PII in application logs
- Store PII in analytics systems
- Share PII with third parties without consent

---

## API Security

### Rate Limiting

✅ **Protect against abuse**
```python
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

# Configure rate limiting
@app.get("/api/equipment", dependencies=[Depends(RateLimiter(times=100, seconds=60))])
async def list_equipment():
    # 100 requests per minute per IP
    pass
```

### CORS Configuration

✅ **Restrictive CORS policy**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lablink.example.com"],  # Specific origins only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600
)
```

❌ **Never use allow_origins=["*"] in production**

### Request Validation

✅ **Validate all inputs**
- Use Pydantic models for request bodies
- Validate query parameters
- Validate headers
- Sanitize file uploads
- Check content-type

```python
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel, validator

class EquipmentCommand(BaseModel):
    equipment_id: str
    command: str

    @validator('equipment_id')
    def validate_equipment_id(cls, v):
        if not v.startswith('scope-') and not v.startswith('gen-'):
            raise ValueError("Invalid equipment ID format")
        return v
```

---

## Secrets Management

### Environment Variables

✅ **Use .env files (never commit)**
```bash
# .env (in .gitignore)
LABLINK_SECRET_KEY=your-secret-key-here
LABLINK_DB_PASSWORD=your-db-password
LABLINK_API_KEY=your-api-key
```

```python
# Load with python-dotenv
from dotenv import load_dotenv
import os

load_dotenv()
SECRET_KEY = os.getenv("LABLINK_SECRET_KEY")
```

### Secret Rotation

**Policy:** Rotate secrets every 90 days or immediately if compromised.

**Process:**
1. Generate new secret
2. Deploy new secret to all instances
3. Update clients gradually
4. Revoke old secret after transition period
5. Audit access logs for old secret usage

### Production Secrets

✅ **Use secret management service**
- AWS Secrets Manager
- Azure Key Vault
- HashiCorp Vault
- Kubernetes Secrets

❌ **Never:**
- Commit secrets to git
- Store secrets in CI/CD logs
- Email or Slack secrets
- Store secrets in container images

---

## CI/CD Security

### Pipeline Security

✅ **Secure CI/CD**
```yaml
# .github/workflows/comprehensive-tests.yml
jobs:
  security-scan:
    - name: Security audit with pip-audit
      run: pip-audit --desc  # Blocks on vulnerabilities

    - name: Scan for secrets
      run: truffleHog --regex --entropy=False .

    - name: SAST with bandit
      run: bandit -r server/ -f json
```

### Dependency Pinning

✅ **Pin versions for reproducibility**
```
# Good: Exact versions in requirements.txt
fastapi==0.109.0

# Also good: Minimum with security fixes
cryptography>=46.0.0  # Security: CVE-XXXX
```

### Branch Protection

✅ **Protect main/production branches**
- Require pull request reviews (min 1)
- Require status checks to pass
- Require security scan to pass
- No direct pushes to main
- Enforce signed commits (recommended)

---

## Deployment Security

### Docker Security

✅ **Secure Docker images**
```dockerfile
# Use official base images
FROM python:3.11-slim

# Don't run as root
RUN useradd -m -u 1000 lablink
USER lablink

# Minimize attack surface
RUN apt-get update && \
    apt-get install -y --no-install-recommends <only-what-needed> && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy only necessary files
COPY --chown=lablink:lablink requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=lablink:lablink server/ ./server/
```

### Network Security

✅ **Defense in depth**
- Firewall rules (allow only necessary ports)
- VPN for internal services
- TLS for all external communication
- Network segmentation (equipment network separate from internet)

### Logging & Monitoring

✅ **Security monitoring**
```python
import logging

# Log security events
logger.info("User login successful", extra={
    "user_id": user.id,
    "ip_address": request.client.host,
    "user_agent": request.headers.get("user-agent")
})

logger.warning("Failed login attempt", extra={
    "username": username,
    "ip_address": request.client.host,
    "attempt_count": attempts
})
```

**Monitor for:**
- Failed authentication attempts
- Permission denials
- Unusual API access patterns
- Large file uploads/downloads
- Equipment command failures

---

## Incident Response

### Security Incident Process

1. **Detect:** Monitor logs, alerts, user reports
2. **Contain:** Isolate affected systems
3. **Investigate:** Analyze logs, determine scope
4. **Eradicate:** Remove threat, patch vulnerabilities
5. **Recover:** Restore services, verify security
6. **Learn:** Post-mortem, update procedures

### Vulnerability Disclosure

**Policy:** Responsible disclosure encouraged

**Process:**
1. Report to security@lablink.example.com
2. Acknowledge within 24 hours
3. Provide updates every 72 hours
4. Aim to fix critical vulnerabilities within 30 days
5. Credit reporter in security advisory (if desired)

### Breach Notification

**Legal Requirements:**
- GDPR: Notify within 72 hours if PII affected
- Document: What, when, who, impact, remediation
- Notify: Affected users, regulators (if required)

---

## Security Checklist

### Before Every Release

- [ ] All tests passing (including security scans)
- [ ] No known critical vulnerabilities
- [ ] Secrets not in code/config
- [ ] Dependencies updated (no outdated packages with known CVEs)
- [ ] CHANGELOG includes security fixes
- [ ] Security documentation updated

### Quarterly Security Review

- [ ] Review dependency vulnerabilities
- [ ] Update dependencies
- [ ] Review access logs for anomalies
- [ ] Test backup/restore procedures
- [ ] Review user permissions (remove unused accounts)
- [ ] Rotate secrets
- [ ] Update security documentation

### Annual Security Audit

- [ ] Professional security audit (recommended)
- [ ] Penetration testing
- [ ] Code review for security issues
- [ ] Infrastructure security review
- [ ] Disaster recovery test
- [ ] Update security policies

---

## Resources

- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **CWE Top 25:** https://cwe.mitre.org/top25/
- **Python Security:** https://python.readthedocs.io/en/stable/library/security.html
- **FastAPI Security:** https://fastapi.tiangolo.com/tutorial/security/
- **NIST Cybersecurity Framework:** https://www.nist.gov/cyberframework

---

## Contact

**Security Team:** security@lablink.example.com
**Security Incidents:** Call escalation procedure
**Vulnerability Reports:** security@lablink.example.com (PGP key available)

---

**Document Revision History:**
- v1.0.0 (2025-11-14): Initial security best practices document (Phase 3)
