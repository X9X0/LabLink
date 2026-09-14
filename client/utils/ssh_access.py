"""Passwordless SSH to a LabLink server, without asking the user to set it up.

The remote update runs with its output captured, so an SSH password prompt can
never be answered -- it would simply hang. That made key-based access a hard
requirement, and the first version of this left the user to arrange it, which
works only for people who already know how. Everyone else met "Permission
denied (publickey,password)" with nothing to do about it.

So the client sets it up itself, the way ``ssh-copy-id`` does: ask for the
password once, generate a key if there isn't one, append the public half to the
server's ``authorized_keys``, and never ask again.

Nothing here stores a password. The password is used for the one connection
that installs the key and is not written anywhere.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from client.utils.proc import no_window_kwargs

logger = logging.getLogger(__name__)

#: ed25519 rather than RSA: a Pi running current OpenSSH refuses SHA-1
#: ``ssh-rsa`` signatures outright, and an older RSA key on the machine is a
#: common reason key auth mysteriously fails.
KEY_PATH = Path.home() / ".ssh" / "id_ed25519"

#: No passphrase. The update has no terminal to ask for one, and a key that
#: cannot be used unattended cannot be used here at all. The key is therefore
#: exactly as trusted as the user's own profile.
KEY_COMMENT = "lablink-automation"


def split_host(ssh_host: str) -> Tuple[Optional[str], str]:
    """``user@host`` into its parts. A bare host has no user."""
    if "@" in ssh_host:
        user, _, host = ssh_host.partition("@")
        return (user or None), host
    return None, ssh_host


def ensure_local_key() -> Optional[Path]:
    """The client's own key, generated on first use.

    Returns:
        Path to the private key, or None if it could not be created.
    """
    if KEY_PATH.exists():
        return KEY_PATH

    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(KEY_PATH),
             "-N", "", "-C", KEY_COMMENT],
            capture_output=True,
            text=True,
            check=True,
            **no_window_kwargs()
        )
        logger.info(f"Generated {KEY_PATH}")
        return KEY_PATH
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Could not generate an SSH key: {e}")
        return None


def public_key_text() -> Optional[str]:
    """The public half, generating the pair if needed."""
    if ensure_local_key() is None:
        return None
    pub = KEY_PATH.with_suffix(KEY_PATH.suffix + ".pub") if KEY_PATH.suffix else Path(
        str(KEY_PATH) + ".pub"
    )
    try:
        return pub.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.error(f"Could not read {pub}: {e}")
        return None


def key_access_works(ssh_host: str, timeout: int = 8) -> bool:
    """Whether we can already get in without a password.

    BatchMode so this answers rather than blocking on a prompt.
    """
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}",
             "-o", "StrictHostKeyChecking=accept-new", ssh_host, "true"],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            **no_window_kwargs()
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def install_public_key(ssh_host: str, password: str, port: int = 22) -> Tuple[bool, str]:
    """Put our public key in the server's authorized_keys, using a password once.

    This is ``ssh-copy-id``, done through paramiko so it works the same on
    Windows, where ssh-copy-id does not ship.

    Args:
        ssh_host: ``user@host``; a bare host cannot be used, since the remote
            username is the one thing that cannot be guessed.
        password: used for this connection only, and not stored.

    Returns:
        (worked, message for the user)
    """
    user, host = split_host(ssh_host)
    if not user:
        return False, (
            f"No SSH user given. Enter it as user@{host} -- the server's "
            f"username cannot be guessed from the connection."
        )

    pub = public_key_text()
    if not pub:
        return False, "Could not create an SSH key on this machine."

    try:
        import paramiko
    except ImportError:
        return False, "paramiko is not installed, so the key cannot be installed."

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=password,
                       timeout=15, allow_agent=False, look_for_keys=False)
    except Exception as e:
        return False, f"Could not sign in to {ssh_host}: {e}"

    try:
        # Appended only if absent, so this is safe to run repeatedly, and the
        # permissions are set because sshd refuses a group-readable file.
        command = (
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
            f"grep -qxF {_quote(pub)} ~/.ssh/authorized_keys || "
            f"echo {_quote(pub)} >> ~/.ssh/authorized_keys"
        )
        _, stdout, stderr = client.exec_command(command, timeout=30)
        status = stdout.channel.recv_exit_status()
        error = stderr.read().decode().strip()
        if status != 0:
            return False, f"Could not write authorized_keys on {host}: {error}"
    finally:
        client.close()

    if not key_access_works(ssh_host):
        return False, (
            f"The key was installed on {host} but still is not accepted. "
            f"Check that the server allows public key authentication."
        )

    return True, f"{ssh_host} no longer needs a password from this machine."


def _quote(value: str) -> str:
    """Single-quote for a POSIX shell. The remote is always POSIX."""
    return "'" + value.replace("'", "'\\''") + "'"
