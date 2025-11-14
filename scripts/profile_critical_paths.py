#!/usr/bin/env python3
"""
Profile Critical Paths Script

Profiles the three critical paths identified in baseline_metrics.md:
1. User login flow
2. Command execution flow
3. Backup creation flow

Usage:
    python scripts/profile_critical_paths.py [--all | --login | --command | --backup]
    python scripts/profile_critical_paths.py --output-dir ./profiles
    python scripts/profile_critical_paths.py --print-stats

Output:
    Saves .prof files to output directory (default: /tmp/lablink_profiles)
    View with: snakeviz /tmp/lablink_profiles/*.prof
"""

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.security.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from server.security.mfa import (
    generate_totp_secret,
    get_current_totp_token,
    verify_totp_token,
)
from server.database.manager import DatabaseManager
from server.database.models import CommandRecord, DatabaseConfig
from server.backup.manager import BackupManager
from server.backup.models import (
    BackupConfig,
    BackupRequest,
    BackupType,
    CompressionType,
)
from server.utils.profiling import profile, profile_async, time_block


# ============================================================================
# Critical Path 1: User Login Flow
# ============================================================================


@profile(output_file=None, print_stats=False)
def profile_login_flow():
    """
    Profile the complete user login flow.

    Steps:
    1. Password verification (~263ms)
    2. TOTP verification (~0.5ms, if MFA enabled)
    3. Token generation (~1ms estimated)

    Expected total: ~264ms
    """
    print("Profiling login flow...")

    # Step 1: Password verification
    with time_block("  1. Password verification"):
        password = "TestPassword123!"
        hashed = hash_password(password)
        verified = verify_password(password, hashed)
        assert verified, "Password verification failed"

    # Step 2: TOTP verification (MFA)
    with time_block("  2. TOTP verification"):
        secret = generate_totp_secret()
        token = get_current_totp_token(secret)
        mfa_verified = verify_totp_token(secret, token)
        assert mfa_verified, "TOTP verification failed"

    # Step 3: Token generation
    with time_block("  3. Token generation"):
        access_token = create_access_token(
            subject="testuser", additional_claims={"role": "admin"}
        )
        assert access_token, "Token generation failed"

    print("✓ Login flow profiling complete")
    return True


# ============================================================================
# Critical Path 2: Command Execution Flow
# ============================================================================


@profile(output_file=None, print_stats=False)
def profile_command_flow():
    """
    Profile the command execution and logging flow.

    Steps:
    1. Model validation (<1μs)
    2. Command execution (hardware-dependent, skipped)
    3. Command logging (~9.5ms)

    Expected total: ~10ms (excluding equipment command)
    """
    print("Profiling command execution flow...")

    # Setup temporary database
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "profile.db")
        config = DatabaseConfig(db_path=db_path)
        manager = DatabaseManager(config=config)

        with time_block("  1. Database initialization"):
            manager.initialize()

        # Profile 100 command logs
        with time_block("  2. Command logging (100 records)"):
            for i in range(100):
                # Step 1: Model validation
                record = CommandRecord(
                    equipment_id=f"scope-{i % 10}",
                    equipment_type="oscilloscope",
                    command="*IDN?",
                    response=f"RIGOL TECHNOLOGIES DS1054Z {i}",
                    execution_time_ms=42.5 + (i * 0.1),
                )

                # Step 3: Command logging
                record_id = manager.log_command(record)
                assert record_id > 0, f"Command logging failed for record {i}"

        # Test query performance
        with time_block("  3. History query"):
            history = manager.get_command_history(equipment_id="scope-0", limit=10)
            assert history.total_count > 0, "History query failed"

    print("✓ Command flow profiling complete")
    return True


# ============================================================================
# Critical Path 3: Backup Creation Flow
# ============================================================================


@profile_async(output_file=None, print_stats=False)
async def profile_backup_flow():
    """
    Profile the backup creation flow.

    Steps:
    1. Model validation (<2μs)
    2. File collection (depends on file count)
    3. Archive creation (depends on data size)
    4. Compression (if enabled)
    5. Verification (if enabled)

    Expected total: Varies with data size
    """
    print("Profiling backup creation flow...")

    # Setup temporary backup environment
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create realistic test data
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir()

        with time_block("  1. Creating test data"):
            # Create 50 config files (~50KB total)
            for i in range(50):
                content = '{"test": true, "id": %d}' % i
                content = content * 20  # ~1KB per file
                (config_dir / f"settings_{i}.json").write_text(content)

        config = BackupConfig(backup_dir=temp_dir)
        manager = BackupManager(config)

        # Test different compression types
        for compression in [
            CompressionType.NONE,
            CompressionType.GZIP,
            CompressionType.BZ2,
        ]:
            with time_block(f"  2. Backup with {compression.value} compression"):
                request = BackupRequest(
                    backup_type=BackupType.CONFIG,
                    compression=compression,
                    description=f"Profile test - {compression.value}",
                    verify_after_backup=True,
                )

                result = await manager.create_backup(request)
                assert result is not None, f"Backup with {compression} failed"

        # Test backup listing
        with time_block("  3. Backup listing"):
            backups = manager.list_backups()
            assert len(backups) >= 3, "Backup listing failed"

    print("✓ Backup flow profiling complete")
    return True


# ============================================================================
# Main Script
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Profile LabLink critical paths",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Profile all critical paths
  python scripts/profile_critical_paths.py --all

  # Profile only login flow
  python scripts/profile_critical_paths.py --login

  # Profile with statistics printed
  python scripts/profile_critical_paths.py --all --print-stats

  # Custom output directory
  python scripts/profile_critical_paths.py --all --output-dir ./profiles
        """,
    )

    parser.add_argument(
        "--all", action="store_true", help="Profile all critical paths (default)"
    )
    parser.add_argument("--login", action="store_true", help="Profile login flow only")
    parser.add_argument(
        "--command", action="store_true", help="Profile command flow only"
    )
    parser.add_argument(
        "--backup", action="store_true", help="Profile backup flow only"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/tmp/lablink_profiles",
        help="Output directory for profile files (default: /tmp/lablink_profiles)",
    )
    parser.add_argument(
        "--print-stats",
        action="store_true",
        help="Print statistics to console after profiling",
    )

    args = parser.parse_args()

    # Set output directory
    import os

    os.environ["LABLINK_PROFILE_DIR"] = args.output_dir
    os.environ["LABLINK_PROFILE_PRINT"] = "true" if args.print_stats else "false"

    # Determine what to profile
    profile_all = args.all or not (args.login or args.command or args.backup)

    print("=" * 80)
    print("LabLink Critical Path Profiling")
    print("=" * 80)
    print(f"Output directory: {args.output_dir}")
    print(f"Print statistics: {args.print_stats}")
    print("=" * 80)
    print()

    try:
        if profile_all or args.login:
            profile_login_flow()
            print()

        if profile_all or args.command:
            profile_command_flow()
            print()

        if profile_all or args.backup:
            asyncio.run(profile_backup_flow())
            print()

        print("=" * 80)
        print("✓ All profiling complete!")
        print("=" * 80)
        print()
        print("View profiles with:")
        print(f"  snakeviz {args.output_dir}/*.prof")
        print()
        print("Or generate flamegraph with py-spy:")
        print(f"  py-spy record -o flamegraph.svg -- python {__file__}")
        print()

    except Exception as e:
        print(f"❌ Profiling failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
