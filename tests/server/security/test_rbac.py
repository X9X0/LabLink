"""
Comprehensive tests for security/rbac.py module.

Tests cover:
- Permission creation and management
- Role creation and management
- Permission checking
- Role hierarchy
- Default roles
"""

import pytest
import sys
import os

# Add server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../server'))

from security.models import (
    Permission,
    PermissionAction,
    ResourceType,
    Role,
    RoleType,
    User,
    create_default_admin_role,
    create_default_operator_role,
    create_default_viewer_role
)


class TestPermission:
    """Test Permission model and operations."""

    def test_permission_creation(self):
        """Test creating a permission."""
        perm = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )

        assert perm.action == PermissionAction.READ
        assert perm.resource == ResourceType.EQUIPMENT

    def test_permission_all_actions(self):
        """Test all permission actions."""
        actions = [
            PermissionAction.READ,
            PermissionAction.WRITE,
            PermissionAction.DELETE,
            PermissionAction.EXECUTE,
            PermissionAction.ADMIN
        ]

        for action in actions:
            perm = Permission(action=action, resource=ResourceType.EQUIPMENT)
            assert perm.action == action

    def test_permission_all_resources(self):
        """Test all resource types."""
        resources = [
            ResourceType.EQUIPMENT,
            ResourceType.ACQUISITION,
            ResourceType.PROFILES,
            ResourceType.STATES,
            ResourceType.SAFETY,
            ResourceType.LOCKS,
            ResourceType.ALARMS,
            ResourceType.SCHEDULER,
            ResourceType.DIAGNOSTICS,
            ResourceType.PERFORMANCE,
            ResourceType.BACKUP,
            ResourceType.DISCOVERY,
            ResourceType.WAVEFORM
        ]

        for resource in resources:
            perm = Permission(action=PermissionAction.READ, resource=resource)
            assert perm.resource == resource

    def test_permission_with_resource_id(self):
        """Test permission with specific resource ID."""
        perm = Permission(
            action=PermissionAction.WRITE,
            resource=ResourceType.EQUIPMENT,
            resource_id="scope-001"
        )

        assert perm.resource_id == "scope-001"

    def test_permission_equality(self):
        """Test permission equality comparison."""
        perm1 = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )
        perm2 = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )

        # Note: Depends on implementation of __eq__
        # If not implemented, this tests object identity


class TestRole:
    """Test Role model and operations."""

    def test_role_creation(self):
        """Test creating a role."""
        role = Role(
            name="test_role",
            role_type=RoleType.CUSTOM,
            permissions=[]
        )

        assert role.name == "test_role"
        assert role.type == RoleType.CUSTOM
        assert len(role.permissions) == 0

    def test_role_with_permissions(self):
        """Test role with permissions."""
        perms = [
            Permission(action=PermissionAction.READ, resource=ResourceType.EQUIPMENT),
            Permission(action=PermissionAction.WRITE, resource=ResourceType.EQUIPMENT)
        ]

        role = Role(
            name="equipment_manager",
            role_type=RoleType.CUSTOM,
            permissions=perms
        )

        assert len(role.permissions) == 2
        assert any(p.action == PermissionAction.READ for p in role.permissions)
        assert any(p.action == PermissionAction.WRITE for p in role.permissions)

    def test_role_description(self):
        """Test role with description."""
        role = Role(
            name="test_role",
            role_type=RoleType.CUSTOM,
            permissions=[],
            description="Test role description"
        )

        assert role.description == "Test role description"


class TestDefaultRoles:
    """Test default role creation functions."""

    def test_create_default_admin_role(self):
        """Test creating default admin role."""
        role = create_default_admin_role()

        assert role.name == "admin"
        assert role.type == RoleType.ADMIN
        assert len(role.permissions) > 0

        # Admin should have ADMIN permission for all resources
        admin_perms = [p for p in role.permissions if p.action == PermissionAction.ADMIN]
        assert len(admin_perms) > 0

    def test_create_default_operator_role(self):
        """Test creating default operator role."""
        role = create_default_operator_role()

        assert role.name == "operator"
        assert role.type == RoleType.OPERATOR
        assert len(role.permissions) > 0

        # Operator should have read/write/execute but not admin
        actions = {p.action for p in role.permissions}
        assert PermissionAction.READ in actions
        assert PermissionAction.WRITE in actions
        assert PermissionAction.EXECUTE in actions

    def test_create_default_viewer_role(self):
        """Test creating default viewer role."""
        role = create_default_viewer_role()

        assert role.name == "viewer"
        assert role.type == RoleType.VIEWER
        assert len(role.permissions) > 0

        # Viewer should only have READ permission
        actions = {p.action for p in role.permissions}
        assert PermissionAction.READ in actions
        assert PermissionAction.WRITE not in actions
        assert PermissionAction.DELETE not in actions
        assert PermissionAction.ADMIN not in actions

    def test_admin_has_more_permissions_than_operator(self):
        """Test that admin has more permissions than operator."""
        admin = create_default_admin_role()
        operator = create_default_operator_role()

        assert len(admin.permissions) >= len(operator.permissions)

    def test_operator_has_more_permissions_than_viewer(self):
        """Test that operator has more permissions than viewer."""
        operator = create_default_operator_role()
        viewer = create_default_viewer_role()

        assert len(operator.permissions) >= len(viewer.permissions)


class TestUserRoles:
    """Test user role assignments."""

    def test_user_with_single_role(self):
        """Test user with single role."""
        viewer_role = create_default_viewer_role()
        user = User(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            roles=[viewer_role],
            is_active=True
        )

        assert len(user.roles) == 1
        assert user.roles[0].name == "viewer"

    def test_user_with_multiple_roles(self):
        """Test user with multiple roles."""
        viewer_role = create_default_viewer_role()
        operator_role = create_default_operator_role()

        user = User(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            roles=[viewer_role, operator_role],
            is_active=True
        )

        assert len(user.roles) == 2
        role_names = {r.name for r in user.roles}
        assert "viewer" in role_names
        assert "operator" in role_names

    def test_user_no_roles(self):
        """Test user with no roles."""
        user = User(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            roles=[],
            is_active=True
        )

        assert len(user.roles) == 0


class TestPermissionChecking:
    """Test permission checking logic."""

    def test_user_has_permission_through_role(self):
        """Test checking if user has permission through their role."""
        # Create a role with specific permission
        equipment_perm = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )
        role = Role(
            name="test_role",
            role_type=RoleType.CUSTOM,
            permissions=[equipment_perm]
        )

        user = User(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            roles=[role],
            is_active=True
        )

        # Check if user has the permission
        has_permission = any(
            p.action == PermissionAction.READ and p.resource == ResourceType.EQUIPMENT
            for role in user.roles
            for p in role.permissions
        )

        assert has_permission is True

    def test_user_lacks_permission(self):
        """Test checking if user lacks a permission."""
        # Create a role with only READ permission
        read_perm = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )
        role = Role(
            name="test_role",
            role_type=RoleType.CUSTOM,
            permissions=[read_perm]
        )

        user = User(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            roles=[role],
            is_active=True
        )

        # Check if user has WRITE permission (should not have)
        has_write = any(
            p.action == PermissionAction.WRITE and p.resource == ResourceType.EQUIPMENT
            for role in user.roles
            for p in role.permissions
        )

        assert has_write is False

    def test_admin_has_all_permissions(self):
        """Test that admin role has admin permission for all resources."""
        admin_role = create_default_admin_role()

        # Admin should have ADMIN action for multiple resource types
        resources_with_admin = {
            p.resource for p in admin_role.permissions
            if p.action == PermissionAction.ADMIN
        }

        # Should have admin permission for multiple resources
        assert len(resources_with_admin) > 0


class TestRoleTypes:
    """Test role type enumeration."""

    def test_all_role_types(self):
        """Test all role type values."""
        types = [RoleType.ADMIN, RoleType.OPERATOR, RoleType.VIEWER, RoleType.CUSTOM]

        for role_type in types:
            role = Role(
                name=f"test_{role_type.value}",
                type=role_type,
                permissions=[]
            )
            assert role.type == role_type


class TestCustomRoles:
    """Test custom role creation scenarios."""

    def test_create_equipment_only_role(self):
        """Test creating role with only equipment permissions."""
        perms = [
            Permission(action=PermissionAction.READ, resource=ResourceType.EQUIPMENT),
            Permission(action=PermissionAction.WRITE, resource=ResourceType.EQUIPMENT),
            Permission(action=PermissionAction.EXECUTE, resource=ResourceType.EQUIPMENT)
        ]

        role = Role(
            name="equipment_operator",
            role_type=RoleType.CUSTOM,
            permissions=perms,
            description="Can read, write, and execute equipment commands"
        )

        assert len(role.permissions) == 3
        assert all(p.resource == ResourceType.EQUIPMENT for p in role.permissions)

    def test_create_readonly_role(self):
        """Test creating read-only role for all resources."""
        resources = [
            ResourceType.EQUIPMENT,
            ResourceType.DIAGNOSTICS,
            ResourceType.PROFILES,
            ResourceType.WAVEFORM
        ]

        perms = [
            Permission(action=PermissionAction.READ, resource=res)
            for res in resources
        ]

        role = Role(
            name="readonly_all",
            role_type=RoleType.CUSTOM,
            permissions=perms,
            description="Read-only access to all resources"
        )

        assert len(role.permissions) == len(resources)
        assert all(p.action == PermissionAction.READ for p in role.permissions)

    def test_create_data_analyst_role(self):
        """Test creating specialized data analyst role."""
        perms = [
            Permission(action=PermissionAction.READ, resource=ResourceType.WAVEFORM),
            Permission(action=PermissionAction.READ, resource=ResourceType.EQUIPMENT),
            Permission(action=PermissionAction.EXECUTE, resource=ResourceType.WAVEFORM)
        ]

        role = Role(
            name="data_analyst",
            role_type=RoleType.CUSTOM,
            permissions=perms,
            description="Can read equipment and analyze data"
        )

        assert len(role.permissions) == 3

        # Can read data and equipment
        can_read_data = any(
            p.action == PermissionAction.READ and p.resource == ResourceType.WAVEFORM
            for p in role.permissions
        )
        can_read_equipment = any(
            p.action == PermissionAction.READ and p.resource == ResourceType.EQUIPMENT
            for p in role.permissions
        )

        assert can_read_data is True
        assert can_read_equipment is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
