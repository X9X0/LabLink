# LabLink Advanced Security System - User Guide

**Version:** v0.23.0
**Last Updated:** 2025-11-13

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Authentication](#authentication)
4. [User Management](#user-management)
5. [Role-Based Access Control](#role-based-access-control)
6. [API Key Management](#api-key-management)
7. [IP Whitelisting](#ip-whitelisting)
8. [Security Audit Logging](#security-audit-logging)
9. [Configuration Reference](#configuration-reference)
10. [API Reference](#api-reference)
11. [Best Practices](#best-practices)
12. [Troubleshooting](#troubleshooting)
13. [Security Compliance](#security-compliance)

---

## Overview

The LabLink Advanced Security System provides enterprise-grade security features for multi-user laboratory environments:

### Key Features

- **JWT Authentication** - Secure token-based authentication with access and refresh tokens
- **Role-Based Access Control (RBAC)** - Granular permissions for equipment and resources
- **User Management** - Complete user lifecycle management with password policies
- **API Key Management** - Programmatic access with scoped permissions
- **IP Whitelisting** - Network-level access control
- **Security Audit Logging** - Comprehensive audit trail for compliance
- **Session Management** - Track and manage active user sessions
- **Account Lockout** - Protection against brute-force attacks

### Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Application                        │
└────────────┬────────────────────────────────────────────────┘
             │
             │ JWT Token / API Key
             ▼
┌─────────────────────────────────────────────────────────────┐
│              Security Middleware Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ IP Whitelist │  │ JWT Validate │  │  API Key     │       │
│  │   Checker    │  │              │  │  Validator   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│              RBAC Permission System                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Permission  │  │    Role      │  │    User      │       │
│  │   Checker    │  │   Manager    │  │   Manager    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Equipment & Resources                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Enable Advanced Security

Edit your `.env` file or set environment variables:

```bash
# Enable advanced security
LABLINK_ENABLE_ADVANCED_SECURITY=true

# JWT secret key (auto-generated if not set, but recommended to set manually)
LABLINK_JWT_SECRET_KEY="your-super-secret-key-here-change-me"

# Token expiration
LABLINK_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
LABLINK_JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Account lockout protection
LABLINK_MAX_FAILED_LOGIN_ATTEMPTS=5
LABLINK_ACCOUNT_LOCKOUT_DURATION_MINUTES=30
```

### 2. Start the Server

On first startup with security enabled, a default admin account is created:

```
Username: admin
Password: LabLink@2025
Email: admin@lablink.local
```

**⚠️ IMPORTANT: Change the default password immediately!**

### 3. Login and Get JWT Token

```bash
curl -X POST http://localhost:8000/api/security/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "LabLink@2025"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id": "abc123",
    "username": "admin",
    "email": "admin@lablink.local",
    "roles": ["admin_role_id"],
    "is_superuser": true
  }
}
```

### 4. Use JWT Token for API Requests

Include the access token in the Authorization header:

```bash
curl http://localhost:8000/api/equipment/list \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 5. Change Default Password

```bash
curl -X POST http://localhost:8000/api/security/users/change-password \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "LabLink@2025",
    "new_password": "NewSecurePassword123!"
  }'
```

---

## Authentication

### JWT Authentication

LabLink uses JSON Web Tokens (JWT) for stateless authentication. Tokens contain:
- User ID and username
- Roles and permissions
- Expiration time
- Authentication method

#### Token Types

1. **Access Token** - Short-lived (default: 30 minutes), used for API requests
2. **Refresh Token** - Long-lived (default: 7 days), used to obtain new access tokens

#### Login Flow

```python
import requests

# 1. Login
response = requests.post(
    "http://localhost:8000/api/security/login",
    json={
        "username": "admin",
        "password": "your_password"
    }
)

tokens = response.json()
access_token = tokens["access_token"]
refresh_token = tokens["refresh_token"]

# 2. Use access token for API calls
headers = {"Authorization": f"Bearer {access_token}"}
equipment = requests.get(
    "http://localhost:8000/api/equipment/list",
    headers=headers
)

# 3. Refresh access token when it expires
new_tokens = requests.post(
    "http://localhost:8000/api/security/refresh",
    json={"refresh_token": refresh_token}
)
```

#### JavaScript/TypeScript Example

```typescript
class LabLinkClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  async login(username: string, password: string) {
    const response = await fetch('http://localhost:8000/api/security/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await response.json();
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;

    // Store tokens securely (e.g., httpOnly cookies)
    return data.user;
  }

  async apiCall(endpoint: string, options: RequestInit = {}) {
    const headers = {
      'Authorization': `Bearer ${this.accessToken}`,
      ...options.headers
    };

    let response = await fetch(endpoint, { ...options, headers });

    // Auto-refresh on 401
    if (response.status === 401) {
      await this.refreshAccessToken();
      response = await fetch(endpoint, { ...options, headers: {
        'Authorization': `Bearer ${this.accessToken}`,
        ...options.headers
      }});
    }

    return response.json();
  }

  async refreshAccessToken() {
    const response = await fetch('http://localhost:8000/api/security/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: this.refreshToken })
    });

    const data = await response.json();
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
  }

  async logout() {
    await fetch('http://localhost:8000/api/security/logout', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.accessToken}` }
    });

    this.accessToken = null;
    this.refreshToken = null;
  }
}
```

### API Key Authentication

For programmatic access (scripts, automation), use API keys:

```bash
# Create API key
curl -X POST http://localhost:8000/api/security/api-keys \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Automation Script",
    "description": "Key for automated testing",
    "scopes": ["equipment:read", "equipment:write"],
    "expires_in_days": 90
  }'
```

Response (key is only shown once!):
```json
{
  "key_id": "key123",
  "key": "lablink_abc123def456...",  // Save this!
  "key_prefix": "lablink_abc1...",
  "name": "Automation Script",
  "scopes": ["equipment:read", "equipment:write"],
  "expires_at": "2026-02-13T12:00:00Z"
}
```

Use API key in requests:
```bash
# Method 1: X-API-Key header
curl http://localhost:8000/api/equipment/list \
  -H "X-API-Key: lablink_abc123def456..."

# Method 2: Authorization header
curl http://localhost:8000/api/equipment/list \
  -H "Authorization: ApiKey lablink_abc123def456..."
```

---

## User Management

### Create User

**Requires:** Superuser privileges

```bash
curl -X POST http://localhost:8000/api/security/users \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "password": "SecurePass123!",
    "full_name": "John Doe",
    "roles": ["operator_role_id"],
    "is_active": true,
    "must_change_password": false
  }'
```

### List Users

```bash
curl http://localhost:8000/api/security/users \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Update User

```bash
curl -X PATCH http://localhost:8000/api/security/users/USER_ID \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "roles": ["admin_role_id"],
    "is_active": true
  }'
```

### Delete User

```bash
curl -X DELETE http://localhost:8000/api/security/users/USER_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Change Own Password

```bash
curl -X POST http://localhost:8000/api/security/users/change-password \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "OldPassword123!",
    "new_password": "NewPassword456!"
  }'
```

### Reset User Password (Admin)

**Requires:** Superuser privileges

```bash
curl -X POST http://localhost:8000/api/security/users/reset-password \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "USER_ID",
    "new_password": "TempPassword123!",
    "must_change_password": true
  }'
```

---

## Role-Based Access Control

### Default Roles

LabLink provides three default roles:

#### 1. Admin
- **Full system access**
- Can manage users, roles, and permissions
- Can control all equipment
- Can view all data and logs

#### 2. Operator
- **Equipment control access**
- Can connect/disconnect equipment
- Can run measurements and tests
- Can create/load profiles
- Cannot manage users or security settings

#### 3. Viewer
- **Read-only access**
- Can view equipment status
- Can view measurements and data
- Cannot control equipment
- Cannot modify settings

### Permission Model

Permissions follow the format: `resource:action`

**Resources:**
- `equipment` - Laboratory equipment
- `acquisition` - Data acquisition
- `profiles` - Equipment profiles
- `states` - Equipment states
- `safety` - Safety limits
- `locks` - Equipment locks
- `alarms` - Alarm system
- `scheduler` - Scheduled operations
- `diagnostics` - Equipment diagnostics
- `performance` - Performance monitoring
- `backup` - Backup & restore
- `discovery` - Equipment discovery
- `waveform` - Waveform analysis
- `analysis` - Data analysis
- `database` - Database operations
- `calibration` - Calibration management
- `testing` - Automated testing
- `users` - User management
- `roles` - Role management
- `api_keys` - API key management
- `settings` - System settings

**Actions:**
- `read` - View/query resources
- `write` - Create/update resources
- `delete` - Delete resources
- `execute` - Execute operations
- `admin` - Full admin access to resource

### Custom Roles

You can create custom roles with specific permissions:

```python
from security import Role, Permission, ResourceType, PermissionAction

# Create custom "Lab Technician" role
lab_tech_role = Role(
    name="lab_technician",
    role_type=RoleType.CUSTOM,
    description="Lab technician with limited equipment access",
    permissions=[
        # Can view all equipment
        Permission(resource=ResourceType.EQUIPMENT, action=PermissionAction.READ),

        # Can only control specific equipment
        Permission(
            resource=ResourceType.EQUIPMENT,
            action=PermissionAction.WRITE,
            resource_id="oscilloscope_1"  # Specific equipment
        ),

        # Can view all waveforms
        Permission(resource=ResourceType.WAVEFORM, action=PermissionAction.READ),

        # Can run diagnostics
        Permission(resource=ResourceType.DIAGNOSTICS, action=PermissionAction.EXECUTE),

        # No access to user management
    ]
)
```

---

## API Key Management

### Best Practices

1. **Principle of Least Privilege** - Grant minimum necessary scopes
2. **Regular Rotation** - Rotate keys every 90 days
3. **Unique Keys** - Different key for each application/script
4. **Secure Storage** - Never commit keys to version control
5. **Monitor Usage** - Review API key usage regularly

### Scopes

API keys can be scoped to specific permissions:

```bash
# Create read-only API key
curl -X POST http://localhost:8000/api/security/api-keys \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Monitoring Script",
    "scopes": ["equipment:read", "acquisition:read"],
    "expires_in_days": 90
  }'

# Create full-access API key (use sparingly!)
curl -X POST http://localhost:8000/api/security/api-keys \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Admin Automation",
    "scopes": ["*"],
    "expires_in_days": 30
  }'
```

### Revoke API Key

```bash
curl -X DELETE http://localhost:8000/api/security/api-keys/KEY_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## IP Whitelisting

### Enable IP Whitelisting

```bash
# In .env file
LABLINK_ENABLE_IP_WHITELIST=true
LABLINK_IP_WHITELIST_ENFORCE=true
```

### Add IP to Whitelist

**Requires:** Superuser privileges

```bash
# Single IP
curl -X POST http://localhost:8000/api/security/ip-whitelist \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "ip_address": "192.168.1.100",
    "is_whitelist": true,
    "description": "Lab workstation",
    "expires_in_days": 365
  }'

# IP range (CIDR)
curl -X POST http://localhost:8000/api/security/ip-whitelist \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "ip_address": "192.168.1.0/24",
    "is_whitelist": true,
    "description": "Lab network"
  }'
```

### Blacklist IP

```bash
curl -X POST http://localhost:8000/api/security/ip-whitelist \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "ip_address": "10.0.0.50",
    "is_whitelist": false,
    "description": "Blocked suspicious IP"
  }'
```

---

## Security Audit Logging

All security events are logged for compliance and troubleshooting:

- Login success/failure
- Logout
- Password changes
- User creation/update/deletion
- Role changes
- Permission grants/revocations
- API key creation/revocation
- Access denials
- IP blocks
- Token expiration

### Query Audit Log

**Requires:** Superuser privileges

```bash
# Get all failed logins in last 24 hours
curl -X POST http://localhost:8000/api/security/audit-log/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "event_type": "login_failed",
    "start_time": "2025-11-12T00:00:00Z",
    "limit": 100
  }'

# Get all actions by specific user
curl -X POST http://localhost:8000/api/security/audit-log/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "username": "john_doe",
    "limit": 100
  }'

# Get all access denials
curl -X POST http://localhost:8000/api/security/audit-log/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "event_type": "access_denied",
    "success": false,
    "limit": 50
  }'
```

---

## Configuration Reference

### Environment Variables

```bash
# Security Enable/Disable
LABLINK_ENABLE_ADVANCED_SECURITY=false    # Enable security system
LABLINK_SECURITY_DB_PATH=./data/security.db

# JWT Configuration
LABLINK_JWT_SECRET_KEY=                    # Auto-generated if not set
LABLINK_JWT_ALGORITHM=HS256
LABLINK_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
LABLINK_JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Password Policy
LABLINK_PASSWORD_MIN_LENGTH=8
LABLINK_PASSWORD_REQUIRE_UPPERCASE=true
LABLINK_PASSWORD_REQUIRE_LOWERCASE=true
LABLINK_PASSWORD_REQUIRE_DIGIT=true
LABLINK_PASSWORD_REQUIRE_SPECIAL=false
LABLINK_PASSWORD_EXPIRATION_DAYS=90

# Account Lockout
LABLINK_ENABLE_ACCOUNT_LOCKOUT=true
LABLINK_MAX_FAILED_LOGIN_ATTEMPTS=5
LABLINK_ACCOUNT_LOCKOUT_DURATION_MINUTES=30

# IP Whitelisting
LABLINK_ENABLE_IP_WHITELIST=false
LABLINK_IP_WHITELIST_ENFORCE=false

# Sessions
LABLINK_SESSION_TIMEOUT_MINUTES=60
LABLINK_MAX_SESSIONS_PER_USER=5

# API Keys
LABLINK_API_KEY_MAX_AGE_DAYS=365
LABLINK_API_KEY_ROTATION_WARNING_DAYS=30

# Audit Logging
LABLINK_ENABLE_SECURITY_AUDIT_LOG=true
LABLINK_SECURITY_LOG_RETENTION_DAYS=90
LABLINK_SECURITY_LOG_FAILED_LOGINS=true
LABLINK_SECURITY_LOG_PERMISSION_DENIALS=true

# Default Admin
LABLINK_CREATE_DEFAULT_ADMIN=true
LABLINK_DEFAULT_ADMIN_USERNAME=admin
LABLINK_DEFAULT_ADMIN_PASSWORD=LabLink@2025
LABLINK_DEFAULT_ADMIN_EMAIL=admin@lablink.local
```

---

## API Reference

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/security/login` | Login with username/password |
| POST | `/api/security/logout` | Logout and invalidate session |
| POST | `/api/security/refresh` | Refresh access token |
| GET | `/api/security/me` | Get current user info |

### User Management Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/security/users` | Create user | Superuser |
| GET | `/api/security/users` | List users | Superuser |
| GET | `/api/security/users/{id}` | Get user | Self or Superuser |
| PATCH | `/api/security/users/{id}` | Update user | Superuser |
| DELETE | `/api/security/users/{id}` | Delete user | Superuser |
| POST | `/api/security/users/change-password` | Change own password | Authenticated |
| POST | `/api/security/users/reset-password` | Reset user password | Superuser |

### Role Management Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/security/roles` | List roles | Authenticated |
| GET | `/api/security/roles/{id}` | Get role | Authenticated |

### API Key Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/security/api-keys` | Create API key | Authenticated |
| GET | `/api/security/api-keys` | List API keys | Authenticated |
| DELETE | `/api/security/api-keys/{id}` | Revoke API key | Owner or Superuser |

### IP Whitelist Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/security/ip-whitelist` | Add IP entry | Superuser |
| GET | `/api/security/ip-whitelist` | List IP entries | Superuser |
| DELETE | `/api/security/ip-whitelist/{id}` | Remove IP entry | Superuser |

### Audit & Status Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/security/audit-log/query` | Query audit log | Superuser |
| GET | `/api/security/status` | Get security status | Superuser |
| GET | `/api/security/sessions` | List all sessions | Superuser |
| GET | `/api/security/sessions/me` | List own sessions | Authenticated |

---

## Best Practices

### 1. Password Security

✅ **Do:**
- Use strong, unique passwords (minimum 12 characters)
- Enable password expiration (90 days recommended)
- Require password complexity (uppercase, lowercase, digits)
- Force password change on first login
- Use a password manager

❌ **Don't:**
- Reuse passwords across systems
- Share passwords between users
- Store passwords in plain text
- Use default passwords in production

### 2. JWT Token Management

✅ **Do:**
- Keep access token lifetime short (15-30 minutes)
- Store tokens securely (httpOnly cookies for web apps)
- Refresh tokens before expiration
- Invalidate tokens on logout
- Use HTTPS in production

❌ **Don't:**
- Store tokens in localStorage (XSS vulnerability)
- Share tokens between users
- Log token values
- Set very long expiration times

### 3. API Key Security

✅ **Do:**
- Rotate API keys regularly (90 days)
- Use minimum necessary scopes
- Monitor API key usage
- Revoke unused keys
- Store keys in environment variables or secrets manager

❌ **Don't:**
- Commit API keys to version control
- Share API keys between applications
- Use wildcard scopes unnecessarily
- Keep keys indefinitely

### 4. Role Assignment

✅ **Do:**
- Follow principle of least privilege
- Review permissions regularly
- Create custom roles for specific needs
- Document role purposes
- Audit role changes

❌ **Don't:**
- Give everyone admin access
- Create overly permissive roles
- Ignore permission errors without investigation

### 5. Network Security

✅ **Do:**
- Enable HTTPS/TLS in production
- Use IP whitelisting for known networks
- Monitor failed login attempts
- Enable account lockout protection
- Review audit logs regularly

❌ **Don't:**
- Expose the server directly to internet without firewall
- Disable IP checking in production
- Ignore security warnings

---

## Troubleshooting

### Login Fails with "Invalid username or password"

**Possible causes:**
1. Incorrect credentials
2. Account disabled
3. Account locked due to failed attempts

**Solution:**
```bash
# Check audit log for failed login attempts
curl -X POST http://localhost:8000/api/security/audit-log/query \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -d '{
    "event_type": "login_failed",
    "username": "problematic_user",
    "limit": 10
  }'

# If account locked, wait for lockout duration or reset as admin
# Lockout duration: LABLINK_ACCOUNT_LOCKOUT_DURATION_MINUTES (default: 30 min)
```

### Token Expired Error (401 Unauthorized)

**Solution:**
Use refresh token to get new access token:

```python
response = requests.post(
    "http://localhost:8000/api/security/refresh",
    json={"refresh_token": refresh_token}
)
new_access_token = response.json()["access_token"]
```

### Permission Denied (403 Forbidden)

**Possible causes:**
1. User lacks required role/permission
2. Resource-specific permission not granted

**Solution:**
```bash
# Check user's roles
curl http://localhost:8000/api/security/users/USER_ID \
  -H "Authorization: Bearer ADMIN_TOKEN"

# Check role permissions
curl http://localhost:8000/api/security/roles/ROLE_ID \
  -H "Authorization: Bearer ADMIN_TOKEN"

# Grant additional role or create custom role with needed permissions
```

### IP Address Blocked

**Solution:**
```bash
# Add IP to whitelist (requires superuser)
curl -X POST http://localhost:8000/api/security/ip-whitelist \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -d '{
    "ip_address": "192.168.1.100",
    "is_whitelist": true,
    "description": "Allowed workstation"
  }'

# Or disable IP whitelisting temporarily
# Set LABLINK_IP_WHITELIST_ENFORCE=false
```

### Cannot Create Admin User on First Start

**Solution:**
```bash
# Check environment variables
LABLINK_ENABLE_ADVANCED_SECURITY=true
LABLINK_CREATE_DEFAULT_ADMIN=true

# Check security database
ls -la ./data/security.db

# If database corrupted, delete and restart server
rm ./data/security.db
# Server will recreate with default admin
```

---

## Security Compliance

### NIST Cybersecurity Framework

LabLink Advanced Security aligns with NIST CSF:

- **Identify**: User and role management, asset tracking
- **Protect**: RBAC, password policies, encryption
- **Detect**: Audit logging, failed login tracking
- **Respond**: Account lockout, IP blocking
- **Recover**: Backup integration, session management

### ISO/IEC 27001

Supports ISO 27001 requirements:

- **A.9.2** User access management
- **A.9.3** User responsibilities (password policies)
- **A.9.4** System access control (RBAC, authentication)
- **A.12.4** Logging and monitoring (audit logs)
- **A.18.1** Compliance (audit trail, retention)

### FDA 21 CFR Part 11

For regulated laboratory environments:

- **Electronic Signatures**: User authentication with audit trail
- **Audit Trails**: Comprehensive security event logging
- **Access Control**: Role-based permissions
- **Data Integrity**: Non-repudiation through JWT signatures

### GDPR Considerations

For EU laboratories:

- **Data Minimization**: Collect only necessary user data
- **Access Control**: RBAC ensures data access control
- **Audit Trail**: Track all data access events
- **Right to Erasure**: User deletion capability
- **Data Portability**: Export audit logs

---

## Migration from Basic to Advanced Security

### Step 1: Enable Advanced Security

```bash
# Add to .env
LABLINK_ENABLE_ADVANCED_SECURITY=true
LABLINK_JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
```

### Step 2: Restart Server

Server will:
1. Create security database
2. Initialize default roles (admin, operator, viewer)
3. Create default admin user

### Step 3: Login as Admin

```bash
curl -X POST http://localhost:8000/api/security/login \
  -d '{"username": "admin", "password": "LabLink@2025"}'
```

### Step 4: Change Admin Password

```bash
curl -X POST http://localhost:8000/api/security/users/change-password \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "old_password": "LabLink@2025",
    "new_password": "YourSecurePassword123!"
  }'
```

### Step 5: Create Users

```bash
# Create operators
curl -X POST http://localhost:8000/api/security/users \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "username": "operator1",
    "email": "op1@lab.com",
    "password": "SecurePass123!",
    "roles": ["operator_role_id"],
    "must_change_password": true
  }'
```

### Step 6: Update Client Applications

Update all client applications to:
1. Authenticate with username/password or API key
2. Include JWT token in API requests
3. Handle token refresh
4. Handle 401/403 errors

---

## Support

For issues or questions:

- **Documentation**: See docs/ directory
- **GitHub Issues**: https://github.com/X9X0/LabLink/issues
- **Security Issues**: Email security@lablink.local (report privately)

---

**Last Updated:** 2025-11-13
**Version:** v0.23.0
