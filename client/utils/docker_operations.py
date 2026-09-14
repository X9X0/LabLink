"""Docker operations utility for server rebuild management."""

import logging
import re
import shlex
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


def update_remote_server(host: str, remote_dir: str, ref: str,
                         no_cache: bool = True) -> DockerRebuildResult:
    """Update a remote LabLink and rebuild its containers, over SSH.

    The Pi already ships the right procedure in ``lablink-update.sh``: fetch,
    check the ref out, then compose down/build/up. Driving that rather than
    sending a second copy of the same commands means a bench Pi updates the
    same way whether somebody ssh'd in and ran it or pressed the button here,
    and there is one place to fix when it is wrong.

    It needs ``remote_dir`` to be a git checkout. The deploy wizard and the
    image builder both used to strip ``.git``, which is why a Pi could not
    update itself; the script says so plainly if it is missing.

    Args:
        host: ``user@hostname`` for ssh
        remote_dir: the LabLink checkout on that host, e.g. ``/opt/lablink``
        ref: tag or branch to put the remote on
        no_cache: rebuild images from scratch

    Returns:
        DockerRebuildResult, with the remote's output either way.
    """
    quoted_dir = shlex.quote(remote_dir)
    quoted_ref = shlex.quote(ref)

    # The script is in the checkout, so run it from there by path rather than
    # relying on it being installed anywhere.
    command = (
        f"cd {quoted_dir} && "
        f"sudo bash ./lablink-update.sh {quoted_ref} --yes && "
        f"echo '=== Resulting version ===' && "
        f"(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD) && "
        f"cat VERSION 2>/dev/null"
    )

    logger.info(f"Updating {host}:{remote_dir} to {ref}...")

    try:
        result = subprocess.run(
            # BatchMode so a host without key auth fails immediately and says
            # so, rather than blocking on a password prompt nobody can see:
            # capture_output means the prompt would never reach the user.
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout + (f"\n=== Stderr ===\n{result.stderr}" if result.stderr else "")
        logger.info(f"Remote update of {host} completed")
        return DockerRebuildResult(success=True, output=output)

    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip()
        if "Permission denied" in detail or "Host key verification" in detail:
            detail += (
                "\n\nThis needs key-based SSH: the update runs without a "
                "terminal, so a password prompt cannot be answered."
            )
        return DockerRebuildResult(
            success=False,
            output=(e.stdout or ""),
            error=detail or f"ssh exited {e.returncode}",
        )
    except FileNotFoundError:
        return DockerRebuildResult(
            success=False, output="", error="ssh was not found on this machine"
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

        # Validate project_dir to prevent shell injection — allow only safe path characters
        if not re.fullmatch(r"[a-zA-Z0-9_./@~-]+", project_dir):
            raise ValueError(f"project_dir contains unsafe characters: {project_dir!r}")

        # Build the command string to execute remotely — use shlex.quote for safety
        no_cache_flag = "--no-cache" if no_cache else ""
        quoted_dir = shlex.quote(project_dir)

        # Create a shell script to run all commands
        commands = (
            f"cd {quoted_dir} && "
            f"echo '=== Stopping containers ===' && "
            f"docker compose down && "
            f"echo '=== Building containers ===' && "
            f"docker compose build {no_cache_flag} && "
            f"echo '=== Starting containers ===' && "
            f"docker compose up -d"
        )

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
