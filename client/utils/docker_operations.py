"""Docker operations utility for server rebuild management."""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DockerRebuildResult:
    """Result of a Docker rebuild operation."""
    success: bool
    output: str
    error: Optional[str] = None


def is_docker_available_locally() -> bool:
    """Check if docker and docker compose are available locally.

    Returns:
        True if both docker and docker compose are available
    """
    try:
        # Check docker
        subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            check=True
        )

        # Check docker compose
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=True
        )

        logger.info("Docker and Docker Compose are available locally")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"Docker not available locally: {e}")
        return False


def rebuild_docker_local(project_dir: str, no_cache: bool = True) -> DockerRebuildResult:
    """Rebuild Docker containers locally.

    Args:
        project_dir: Path to docker-compose.yml directory
        no_cache: Use --no-cache flag (default: True)

    Returns:
        DockerRebuildResult with success status and output
    """
    try:
        output_lines = []

        # Step 1: Stop containers
        logger.info("Stopping Docker containers...")
        result = subprocess.run(
            ["docker", "compose", "down"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
        output_lines.append("=== Docker Compose Down ===")
        output_lines.append(result.stdout)
        output_lines.append(result.stderr)

        # Step 2: Build containers
        logger.info(f"Building Docker containers (no_cache={no_cache})...")
        build_cmd = ["docker", "compose", "build"]
        if no_cache:
            build_cmd.append("--no-cache")

        result = subprocess.run(
            build_cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
        output_lines.append("\n=== Docker Compose Build ===")
        output_lines.append(result.stdout)
        output_lines.append(result.stderr)

        # Step 3: Start containers
        logger.info("Starting Docker containers...")
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
        output_lines.append("\n=== Docker Compose Up ===")
        output_lines.append(result.stdout)
        output_lines.append(result.stderr)

        full_output = '\n'.join(output_lines)
        logger.info("Docker rebuild completed successfully")
        return DockerRebuildResult(
            success=True,
            output=full_output
        )

    except subprocess.CalledProcessError as e:
        error_msg = f"Docker command failed: {e.stderr}"
        logger.error(error_msg)
        return DockerRebuildResult(
            success=False,
            output=e.stdout or "",
            error=error_msg
        )
    except Exception as e:
        error_msg = f"Unexpected error during Docker rebuild: {str(e)}"
        logger.error(error_msg)
        return DockerRebuildResult(
            success=False,
            output="",
            error=error_msg
        )


def rebuild_docker_ssh(host: str, project_dir: str, no_cache: bool = True) -> DockerRebuildResult:
    """Rebuild Docker containers via SSH.

    Args:
        host: SSH host (user@hostname)
        project_dir: Path to docker-compose.yml on remote host
        no_cache: Use --no-cache flag (default: True)

    Returns:
        DockerRebuildResult with success status and output
    """
    try:
        output_lines = []

        # Build the command string to execute remotely
        no_cache_flag = "--no-cache" if no_cache else ""

        # Create a shell script to run all commands
        commands = f"""
cd {project_dir} && \
echo "=== Stopping containers ===" && \
docker compose down && \
echo "=== Building containers ===" && \
docker compose build {no_cache_flag} && \
echo "=== Starting containers ===" && \
docker compose up -d
"""

        logger.info(f"Rebuilding Docker on {host}...")

        # Execute via SSH
        result = subprocess.run(
            ["ssh", host, commands],
            capture_output=True,
            text=True,
            check=True
        )

        output_lines.append(f"=== SSH Output from {host} ===")
        output_lines.append(result.stdout)
        if result.stderr:
            output_lines.append("=== Stderr ===")
            output_lines.append(result.stderr)

        full_output = '\n'.join(output_lines)
        logger.info(f"Docker rebuild on {host} completed successfully")
        return DockerRebuildResult(
            success=True,
            output=full_output
        )

    except subprocess.CalledProcessError as e:
        error_msg = f"SSH command failed: {e.stderr}"
        logger.error(error_msg)
        return DockerRebuildResult(
            success=False,
            output=e.stdout or "",
            error=error_msg
        )
    except Exception as e:
        error_msg = f"Unexpected error during SSH Docker rebuild: {str(e)}"
        logger.error(error_msg)
        return DockerRebuildResult(
            success=False,
            output="",
            error=error_msg
        )


def generate_rebuild_instructions(project_dir: str, ref: str) -> str:
    """Generate manual rebuild instructions for copy-paste.

    Args:
        project_dir: Path to docker-compose.yml directory
        ref: Git reference (tag or branch)

    Returns:
        Formatted instructions string
    """
    return f"""To update LabLink server:

1. Stop containers:
   cd {project_dir}
   docker compose down

2. Update code:
   git checkout {ref}
   git pull origin {ref}

3. Rebuild and restart:
   docker compose build --no-cache
   docker compose up -d

4. Verify:
   Check System Management panel for new version"""
