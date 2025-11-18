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


# Global update manager instance
update_manager = UpdateManager()
