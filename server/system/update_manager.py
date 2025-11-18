"""System update manager for LabLink server."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .version import __version__, compare_versions

logger = logging.getLogger(__name__)


class UpdateStatus(str, Enum):
    """Update status states."""

    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    RESTARTING = "restarting"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"


class UpdateManager:
    """Manages system updates for LabLink server."""

    def __init__(self):
        """Initialize update manager."""
        self.status = UpdateStatus.IDLE
        self.current_version = __version__
        self.available_version: Optional[str] = None
        self.update_progress = 0.0
        self.update_message = ""
        self.update_logs: List[str] = []
        self.update_error: Optional[str] = None

        # Get root directory
        self.root_dir = Path(__file__).parent.parent.parent
        self.backup_dir = self.root_dir / "backups" / "system"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Check if running in Docker
        self.is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER")

        # Check if git repository exists
        self.is_git_repo = (self.root_dir / ".git").exists()

        # Auto-rebuild configuration
        self.auto_rebuild_enabled = False
        self.rebuild_command: Optional[str] = None
        self.last_update_check: Optional[datetime] = None

        # Scheduled update checking
        self.scheduled_check_enabled = False
        self.check_interval_hours = 24  # Default: check once per day
        self.scheduled_check_task: Optional[asyncio.Task] = None
        self.git_remote = "origin"
        self.git_branch: Optional[str] = None

    def _add_log(self, message: str, level: str = "info"):
        """Add a log entry.

        Args:
            message: Log message
            level: Log level (info, warning, error)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level.upper()}] {message}"
        self.update_logs.append(log_entry)

        # Also log to logger
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def get_status(self) -> Dict:
        """Get current update status.

        Returns:
            Dictionary with update status information
        """
        return {
            "status": self.status,
            "current_version": self.current_version,
            "available_version": self.available_version,
            "progress": self.update_progress,
            "message": self.update_message,
            "logs": self.update_logs[-50:],  # Last 50 log entries
            "error": self.update_error,
            "is_docker": self.is_docker,
            "is_git_repo": self.is_git_repo,
            "auto_rebuild_enabled": self.auto_rebuild_enabled,
            "last_update_check": self.last_update_check.isoformat() if self.last_update_check else None,
        }

    def configure_auto_rebuild(self, enabled: bool, command: Optional[str] = None) -> Dict:
        """Configure automatic rebuild after updates.

        Args:
            enabled: Enable/disable auto-rebuild
            command: Optional custom rebuild command (default: docker compose rebuild)

        Returns:
            Configuration result
        """
        self.auto_rebuild_enabled = enabled

        if command:
            self.rebuild_command = command
        elif self.is_docker:
            # Default Docker rebuild command from host
            self.rebuild_command = "docker compose build && docker compose up -d"
        else:
            self.rebuild_command = None

        self._add_log(f"Auto-rebuild {'enabled' if enabled else 'disabled'}")
        if self.rebuild_command:
            self._add_log(f"Rebuild command: {self.rebuild_command}")

        return {
            "success": True,
            "auto_rebuild_enabled": self.auto_rebuild_enabled,
            "rebuild_command": self.rebuild_command,
        }

    async def execute_rebuild(self) -> Dict:
        """Execute Docker rebuild and restart.

        This attempts to rebuild the Docker containers from within the container.
        This requires the Docker socket to be mounted or SSH access to the host.

        Returns:
            Rebuild result
        """
        if not self.is_docker:
            return {
                "success": False,
                "error": "Not running in Docker - rebuild not applicable",
            }

        self._add_log("Starting Docker rebuild...")
        self.status = UpdateStatus.RESTARTING
        self.update_progress = 60.0

        try:
            # Check if we can access Docker socket (mounted volume)
            docker_socket = Path("/var/run/docker.sock")

            if docker_socket.exists():
                self._add_log("Docker socket detected - attempting rebuild from container")

                # Try to use docker CLI from within container
                # This requires docker client to be installed in the container
                result = subprocess.run(
                    ["which", "docker"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    # Docker CLI available - can rebuild
                    self._add_log("Executing: docker compose build")
                    result = subprocess.run(
                        ["docker", "compose", "build"],
                        cwd=self.root_dir,
                        capture_output=True,
                        text=True,
                        timeout=600,  # 10 minute timeout
                    )

                    if result.returncode != 0:
                        raise Exception(f"Docker build failed: {result.stderr}")

                    self._add_log("Build complete - restarting containers")
                    self.update_progress = 90.0

                    # Restart containers
                    result = subprocess.run(
                        ["docker", "compose", "up", "-d"],
                        cwd=self.root_dir,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if result.returncode != 0:
                        raise Exception(f"Docker restart failed: {result.stderr}")

                    self._add_log("✅ Rebuild and restart complete!")
                    self.update_progress = 100.0
                    self.status = UpdateStatus.COMPLETED

                    return {
                        "success": True,
                        "message": "Docker containers rebuilt and restarted successfully",
                    }
                else:
                    raise Exception("Docker CLI not available in container")
            else:
                raise Exception("Docker socket not mounted - cannot rebuild from container")

        except Exception as e:
            error_msg = f"Rebuild failed: {str(e)}"
            self._add_log(error_msg, level="error")
            self.update_error = str(e)
            self.status = UpdateStatus.FAILED

            return {
                "success": False,
                "error": str(e),
                "manual_instructions": (
                    "Please run these commands on the Docker host:\n"
                    f"cd {self.root_dir}\n"
                    "docker compose build\n"
                    "docker compose up -d"
                ),
            }

    async def check_for_updates(
        self, git_remote: str = "origin", git_branch: Optional[str] = None
    ) -> Dict:
        """Check if updates are available.

        Args:
            git_remote: Git remote name (default: origin)
            git_branch: Git branch to check (default: current branch)

        Returns:
            Dictionary with update availability information
        """
        self.status = UpdateStatus.CHECKING
        self.update_logs = []
        self.update_error = None
        self.last_update_check = datetime.now()
        self._add_log("Checking for updates...")

        try:
            if not self.is_git_repo:
                self._add_log(
                    "Not a git repository - manual updates only", level="warning"
                )
                self.status = UpdateStatus.IDLE
                return {
                    "updates_available": False,
                    "current_version": self.current_version,
                    "message": "Not a git repository - cannot auto-update",
                }

            # Fetch latest changes from remote
            self._add_log(f"Fetching from remote '{git_remote}'...")
            result = subprocess.run(
                ["git", "fetch", git_remote],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise Exception(f"Git fetch failed: {result.stderr}")

            # Get current branch if not specified
            if not git_branch:
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                )
                git_branch = result.stdout.strip()

            self._add_log(f"Current branch: {git_branch}")

            # Check if there are new commits
            result = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..{git_remote}/{git_branch}"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise Exception(f"Git rev-list failed: {result.stderr}")

            new_commits = int(result.stdout.strip())

            if new_commits > 0:
                self._add_log(f"Found {new_commits} new commit(s)")
                # Try to read VERSION from remote
                result = subprocess.run(
                    ["git", "show", f"{git_remote}/{git_branch}:VERSION"],
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    remote_version = result.stdout.strip()
                    self.available_version = remote_version
                    self._add_log(f"Available version: {remote_version}")

                    # Compare versions
                    if compare_versions(remote_version, self.current_version) > 0:
                        self._add_log("Update available!")
                        self.status = UpdateStatus.IDLE
                        return {
                            "updates_available": True,
                            "current_version": self.current_version,
                            "available_version": remote_version,
                            "commits_behind": new_commits,
                        }

            self._add_log("No updates available")
            self.status = UpdateStatus.IDLE
            return {
                "updates_available": False,
                "current_version": self.current_version,
                "message": "Already up to date",
            }

        except Exception as e:
            error_msg = f"Failed to check for updates: {str(e)}"
            self._add_log(error_msg, level="error")
            self.update_error = str(e)
            self.status = UpdateStatus.FAILED
            return {
                "updates_available": False,
                "current_version": self.current_version,
                "error": str(e),
            }

    async def start_update(
        self, git_remote: str = "origin", git_branch: Optional[str] = None
    ) -> Dict:
        """Start the update process.

        Args:
            git_remote: Git remote name (default: origin)
            git_branch: Git branch to pull from (default: current branch)

        Returns:
            Dictionary with update result
        """
        if self.status not in [UpdateStatus.IDLE, UpdateStatus.FAILED]:
            return {
                "success": False,
                "error": f"Cannot start update - current status: {self.status}",
            }

        self.status = UpdateStatus.DOWNLOADING
        self.update_progress = 0.0
        self.update_logs = []
        self.update_error = None
        self._add_log("Starting update process...")

        try:
            if not self.is_git_repo:
                raise Exception("Not a git repository - cannot auto-update")

            # Create backup
            self._add_log("Creating backup...")
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.backup_dir / backup_name

            # Save current git commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )
            current_commit = result.stdout.strip()

            backup_info = {
                "timestamp": datetime.now().isoformat(),
                "version": self.current_version,
                "commit": current_commit,
            }

            backup_path.mkdir(parents=True, exist_ok=True)
            with open(backup_path / "backup_info.json", "w") as f:
                json.dump(backup_info, f, indent=2)

            self._add_log(f"Backup created: {backup_name}")
            self.update_progress = 10.0

            # Get current branch if not specified
            if not git_branch:
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                )
                git_branch = result.stdout.strip()

            # Pull latest changes
            self._add_log(f"Pulling latest changes from {git_remote}/{git_branch}...")
            self.status = UpdateStatus.DOWNLOADING

            result = subprocess.run(
                ["git", "pull", git_remote, git_branch],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise Exception(f"Git pull failed: {result.stderr}")

            self._add_log("Successfully pulled latest changes")
            self.update_progress = 40.0

            # Check if we're in Docker and need to rebuild
            if self.is_docker:
                self._add_log(
                    "Running in Docker - rebuild required", level="warning"
                )
                self.status = UpdateStatus.INSTALLING

                # Check if auto-rebuild is enabled
                if self.auto_rebuild_enabled:
                    self._add_log("Auto-rebuild enabled - attempting automatic rebuild")
                    self.update_progress = 50.0

                    # Attempt automatic rebuild
                    rebuild_result = await self.execute_rebuild()

                    if rebuild_result.get("success"):
                        # Rebuild successful!
                        return rebuild_result
                    else:
                        # Rebuild failed - provide manual instructions
                        self._add_log(
                            "Auto-rebuild failed - manual rebuild required",
                            level="warning",
                        )
                        return {
                            "success": True,
                            "message": "Update downloaded but auto-rebuild failed.",
                            "requires_rebuild": True,
                            "rebuild_command": "sudo docker compose build && sudo systemctl restart lablink.service",
                            "rebuild_error": rebuild_result.get("error"),
                            "manual_instructions": rebuild_result.get(
                                "manual_instructions"
                            ),
                        }
                else:
                    # Auto-rebuild not enabled - provide manual instructions
                    self._add_log(
                        "Server update downloaded. Docker rebuild needed to apply changes."
                    )
                    self._add_log(
                        "Run: sudo docker compose build && sudo systemctl restart lablink.service"
                    )
                    self.update_progress = 100.0
                    self.status = UpdateStatus.COMPLETED

                    return {
                        "success": True,
                        "message": "Update downloaded. Docker rebuild required.",
                        "requires_rebuild": True,
                        "rebuild_command": "sudo docker compose build && sudo systemctl restart lablink.service",
                    }

            # Not in Docker - can try to restart directly
            self._add_log("Update complete - restart required")
            self.update_progress = 100.0
            self.status = UpdateStatus.COMPLETED

            return {
                "success": True,
                "message": "Update complete - restart server to apply changes",
                "requires_rebuild": False,
            }

        except Exception as e:
            error_msg = f"Update failed: {str(e)}"
            self._add_log(error_msg, level="error")
            self.update_error = str(e)
            self.status = UpdateStatus.FAILED

            return {"success": False, "error": str(e)}

    async def rollback(self) -> Dict:
        """Rollback to previous version.

        Returns:
            Dictionary with rollback result
        """
        self.status = UpdateStatus.ROLLING_BACK
        self._add_log("Starting rollback...")

        try:
            if not self.is_git_repo:
                raise Exception("Not a git repository - cannot rollback")

            # Find latest backup
            backups = sorted(self.backup_dir.glob("backup_*"), reverse=True)
            if not backups:
                raise Exception("No backups found")

            latest_backup = backups[0]
            backup_info_file = latest_backup / "backup_info.json"

            if not backup_info_file.exists():
                raise Exception("Backup info not found")

            with open(backup_info_file) as f:
                backup_info = json.load(f)

            rollback_commit = backup_info.get("commit")
            if not rollback_commit:
                raise Exception("Backup commit hash not found")

            self._add_log(f"Rolling back to commit: {rollback_commit}")

            # Reset to previous commit
            result = subprocess.run(
                ["git", "reset", "--hard", rollback_commit],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise Exception(f"Git reset failed: {result.stderr}")

            self._add_log("Rollback complete - restart required")
            self.status = UpdateStatus.COMPLETED

            return {
                "success": True,
                "message": "Rollback complete - restart to apply",
                "rolled_back_to": backup_info.get("version", "unknown"),
            }

        except Exception as e:
            error_msg = f"Rollback failed: {str(e)}"
            self._add_log(error_msg, level="error")
            self.update_error = str(e)
            self.status = UpdateStatus.FAILED

            return {"success": False, "error": str(e)}

    async def _scheduled_update_check_loop(self):
        """Background task for scheduled update checking."""
        logger.info(
            f"Starting scheduled update checks (interval: {self.check_interval_hours}h)"
        )

        while self.scheduled_check_enabled:
            try:
                # Check for updates
                logger.info("Running scheduled update check...")
                result = await self.check_for_updates(
                    git_remote=self.git_remote, git_branch=self.git_branch
                )

                if result.get("updates_available"):
                    logger.info(
                        f"Update available: {result.get('available_version')} "
                        f"({result.get('commits_behind', 0)} commits behind)"
                    )
                else:
                    logger.info("No updates available")

            except Exception as e:
                logger.error(f"Scheduled update check failed: {e}")

            # Wait for next check interval
            await asyncio.sleep(self.check_interval_hours * 3600)

        logger.info("Scheduled update checking stopped")

    def configure_scheduled_checks(
        self,
        enabled: bool,
        interval_hours: int = 24,
        git_remote: str = "origin",
        git_branch: Optional[str] = None,
    ) -> Dict:
        """Configure scheduled update checking.

        Args:
            enabled: Enable/disable scheduled checks
            interval_hours: Hours between checks (default: 24)
            git_remote: Git remote to check (default: origin)
            git_branch: Git branch to check (default: current branch)

        Returns:
            Configuration result
        """
        self.scheduled_check_enabled = enabled
        self.check_interval_hours = interval_hours
        self.git_remote = git_remote
        if git_branch:
            self.git_branch = git_branch

        self._add_log(f"Scheduled checks {'enabled' if enabled else 'disabled'}")
        if enabled:
            self._add_log(f"Check interval: {interval_hours} hours")
            self._add_log(f"Monitoring: {git_remote}/{git_branch or 'current branch'}")

        return {
            "success": True,
            "scheduled_check_enabled": self.scheduled_check_enabled,
            "check_interval_hours": self.check_interval_hours,
            "git_remote": self.git_remote,
            "git_branch": self.git_branch,
        }

    async def start_scheduled_checks(self):
        """Start the scheduled update checking task."""
        if not self.scheduled_check_enabled:
            return {
                "success": False,
                "error": "Scheduled checks not enabled - configure first",
            }

        if self.scheduled_check_task and not self.scheduled_check_task.done():
            return {
                "success": False,
                "error": "Scheduled checks already running",
            }

        # Start background task
        self.scheduled_check_task = asyncio.create_task(
            self._scheduled_update_check_loop()
        )

        self._add_log("Started scheduled update checks")
        logger.info("Scheduled update checks started")

        return {
            "success": True,
            "message": "Scheduled update checks started",
        }

    async def stop_scheduled_checks(self):
        """Stop the scheduled update checking task."""
        if not self.scheduled_check_task or self.scheduled_check_task.done():
            return {
                "success": False,
                "error": "Scheduled checks not running",
            }

        # Stop background task
        self.scheduled_check_enabled = False

        # Wait for task to complete
        try:
            await asyncio.wait_for(self.scheduled_check_task, timeout=5.0)
        except asyncio.TimeoutError:
            self.scheduled_check_task.cancel()
            try:
                await self.scheduled_check_task
            except asyncio.CancelledError:
                pass

        self._add_log("Stopped scheduled update checks")
        logger.info("Scheduled update checks stopped")

        return {
            "success": True,
            "message": "Scheduled update checks stopped",
        }


# Global update manager instance
update_manager = UpdateManager()
