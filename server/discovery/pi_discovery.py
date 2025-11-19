"""Raspberry Pi network discovery for LabLink."""

import asyncio
import ipaddress
import logging
import socket
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


# Raspberry Pi vendor MAC address prefixes
RPI_MAC_PREFIXES = [
    "B8:27:EB",  # Raspberry Pi Foundation - older models
    "DC:A6:32",  # Raspberry Pi Foundation - newer models
    "E4:5F:01",  # Raspberry Pi Foundation - Pi 4 and newer
    "D8:3A:DD",  # Raspberry Pi Foundation - some Pi models
    "28:CD:C1",  # Raspberry Pi Foundation - Zero W and others
]


@dataclass
class DiscoveredPi:
    """Represents a discovered Raspberry Pi."""

    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    is_lablink: bool = False
    lablink_version: Optional[str] = None
    lablink_name: Optional[str] = None
    os_info: Optional[str] = None
    reachable: bool = True
    response_time_ms: Optional[float] = None


class PiDiscovery:
    """Network discovery for Raspberry Pi devices."""

    def __init__(self):
        """Initialize Pi discovery."""
        self.discovered_pis: List[DiscoveredPi] = []
        self.scan_in_progress = False

    async def discover_network(
        self, network: Optional[str] = None, timeout: float = 2.0
    ) -> List[DiscoveredPi]:
        """Discover Raspberry Pis on the network.

        Args:
            network: Network to scan (CIDR notation, e.g., "192.168.1.0/24")
                    If None, auto-detect local network
            timeout: Timeout for each host check in seconds

        Returns:
            List of discovered Raspberry Pis
        """
        if self.scan_in_progress:
            logger.warning("Discovery scan already in progress")
            return self.discovered_pis

        self.scan_in_progress = True
        self.discovered_pis = []

        try:
            # Auto-detect network if not specified
            if not network:
                network = self._get_local_network()

            logger.info(f"Scanning network: {network}")

            # Parse network CIDR
            try:
                net = ipaddress.ip_network(network, strict=False)
            except ValueError as e:
                logger.error(f"Invalid network CIDR: {e}")
                return []

            # Scan network for hosts
            hosts = [str(ip) for ip in net.hosts()]

            # Limit scan to reasonable size (Class C)
            if len(hosts) > 254:
                logger.warning(f"Network too large ({len(hosts)} hosts), limiting to first 254")
                hosts = hosts[:254]

            logger.info(f"Scanning {len(hosts)} hosts...")

            # Scan hosts in parallel (batches of 20 to avoid overwhelming network)
            batch_size = 20
            for i in range(0, len(hosts), batch_size):
                batch = hosts[i:i + batch_size]
                tasks = [self._check_host(ip, timeout) for ip in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, DiscoveredPi):
                        self.discovered_pis.append(result)

            logger.info(f"Discovery complete: found {len(self.discovered_pis)} Raspberry Pi(s)")

        except Exception as e:
            logger.error(f"Error during network discovery: {e}")

        finally:
            self.scan_in_progress = False

        return self.discovered_pis

    def _get_local_network(self) -> str:
        """Auto-detect local network CIDR.

        Returns:
            Network CIDR (e.g., "192.168.1.0/24")
        """
        try:
            # Get local IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()

            # Assume /24 network (Class C)
            network = ".".join(local_ip.split(".")[:-1]) + ".0/24"
            logger.info(f"Auto-detected local network: {network}")
            return network

        except Exception as e:
            logger.error(f"Failed to auto-detect network: {e}")
            return "192.168.1.0/24"  # Default fallback

    async def _check_host(self, ip: str, timeout: float) -> Optional[DiscoveredPi]:
        """Check if host is a Raspberry Pi and probe for LabLink.

        Args:
            ip: IP address to check
            timeout: Timeout in seconds

        Returns:
            DiscoveredPi if Pi is found, None otherwise
        """
        try:
            # Quick ping check first
            reachable, response_time = await self._ping_host(ip, timeout)

            if not reachable:
                return None

            # Get MAC address and hostname
            mac_address = await self._get_mac_address(ip)
            hostname = await self._get_hostname(ip)

            # Check if MAC address matches Raspberry Pi vendor prefixes
            is_pi = False
            if mac_address:
                mac_upper = mac_address.upper()
                for prefix in RPI_MAC_PREFIXES:
                    if mac_upper.startswith(prefix):
                        is_pi = True
                        break

            # If MAC doesn't match, check hostname for pi-like patterns
            if not is_pi and hostname:
                hostname_lower = hostname.lower()
                if any(pattern in hostname_lower for pattern in ["raspberry", "raspberrypi", "pi"]):
                    is_pi = True

            # If not a Pi, skip further probing
            if not is_pi:
                return None

            # Probe for LabLink
            is_lablink, lablink_info = await self._probe_lablink(ip, timeout)

            pi = DiscoveredPi(
                ip_address=ip,
                hostname=hostname,
                mac_address=mac_address,
                is_lablink=is_lablink,
                lablink_version=lablink_info.get("version") if lablink_info else None,
                lablink_name=lablink_info.get("name") if lablink_info else None,
                reachable=True,
                response_time_ms=response_time,
            )

            logger.info(
                f"Found Raspberry Pi: {ip} ({hostname})"
                + (f" - LabLink v{pi.lablink_version}" if is_lablink else " - Regular Pi OS")
            )

            return pi

        except Exception as e:
            logger.debug(f"Error checking host {ip}: {e}")
            return None

    async def _ping_host(self, ip: str, timeout: float) -> tuple[bool, Optional[float]]:
        """Ping a host to check if it's reachable.

        Args:
            ip: IP address to ping
            timeout: Timeout in seconds

        Returns:
            Tuple of (is_reachable, response_time_ms)
        """
        try:
            # Use system ping command (works on Linux)
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout + 1
            )

            if process.returncode == 0:
                # Parse response time from ping output
                output = stdout.decode()
                if "time=" in output:
                    try:
                        time_str = output.split("time=")[1].split()[0]
                        response_time = float(time_str)
                        return True, response_time
                    except (IndexError, ValueError):
                        pass

                return True, None

            return False, None

        except asyncio.TimeoutError:
            return False, None
        except Exception as e:
            logger.debug(f"Ping error for {ip}: {e}")
            return False, None

    async def _get_mac_address(self, ip: str) -> Optional[str]:
        """Get MAC address for an IP using ARP.

        Args:
            ip: IP address

        Returns:
            MAC address or None
        """
        try:
            # Try to read from ARP cache
            cmd = ["arp", "-n", ip]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=2.0
            )

            output = stdout.decode()

            # Parse MAC address from ARP output
            # Format: "192.168.1.100 ... B8:27:EB:XX:XX:XX ..."
            for line in output.split("\n"):
                if ip in line:
                    parts = line.split()
                    for part in parts:
                        if ":" in part and len(part) == 17:  # MAC address format
                            return part.upper()

            return None

        except Exception as e:
            logger.debug(f"MAC address lookup error for {ip}: {e}")
            return None

    async def _get_hostname(self, ip: str) -> Optional[str]:
        """Get hostname for an IP.

        Args:
            ip: IP address

        Returns:
            Hostname or None
        """
        try:
            # Reverse DNS lookup
            loop = asyncio.get_event_loop()
            hostname, _, _ = await asyncio.wait_for(
                loop.run_in_executor(None, socket.gethostbyaddr, ip),
                timeout=2.0
            )
            return hostname

        except (socket.herror, socket.gaierror, asyncio.TimeoutError):
            return None
        except Exception as e:
            logger.debug(f"Hostname lookup error for {ip}: {e}")
            return None

    async def _probe_lablink(self, ip: str, timeout: float) -> tuple[bool, Optional[Dict]]:
        """Probe an IP for LabLink server.

        Args:
            ip: IP address to probe
            timeout: Timeout in seconds

        Returns:
            Tuple of (is_lablink, lablink_info)
        """
        try:
            # Try to connect to LabLink API on port 8000
            url = f"http://{ip}:8000/api"

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=timeout)
            )

            if response.status_code == 200:
                data = response.json()

                # Check if response looks like LabLink
                if "server" in data or "version" in data:
                    return True, {
                        "version": data.get("version", "unknown"),
                        "name": data.get("server", {}).get("name", "LabLink"),
                    }

            # Also try health endpoint
            health_url = f"http://{ip}:8000/health"
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(health_url, timeout=timeout)
            )

            if response.status_code == 200:
                # Health endpoint exists, likely LabLink
                # Try version endpoint
                version_url = f"http://{ip}:8000/api/system/version"
                try:
                    version_response = await loop.run_in_executor(
                        None,
                        lambda: requests.get(version_url, timeout=timeout)
                    )
                    if version_response.status_code == 200:
                        version_data = version_response.json()
                        return True, {
                            "version": version_data.get("version", "unknown"),
                            "name": "LabLink",
                        }
                except:
                    pass

                return True, {"version": "unknown", "name": "LabLink"}

            return False, None

        except requests.RequestException:
            return False, None
        except Exception as e:
            logger.debug(f"LabLink probe error for {ip}: {e}")
            return False, None


# Global discovery instance
pi_discovery = PiDiscovery()
