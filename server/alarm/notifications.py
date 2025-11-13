"""Notification handling for alarms."""

import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

from .models import AlarmEvent, AlarmConfig, NotificationConfig

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages alarm notifications via multiple channels."""

    def __init__(self):
        """Initialize notification manager."""
        self.config = NotificationConfig()
        self._last_notification: dict = defaultdict(lambda: datetime.min)
        self._notification_count: dict = defaultdict(int)

    def configure(self, config: NotificationConfig):
        """Update notification configuration."""
        self.config = config
        logger.info("Notification configuration updated")

    async def send_notification(self, method: str, event: AlarmEvent, alarm_config: AlarmConfig):
        """
        Send alarm notification via specified method.

        Args:
            method: Notification method (email, sms, websocket)
            event: Alarm event
            alarm_config: Alarm configuration
        """
        # Check throttling
        if not self._should_send(alarm_config.alarm_id):
            logger.debug(f"Notification throttled for alarm {alarm_config.alarm_id}")
            return

        # Send via appropriate channel
        if method == "email":
            await self._send_email(event, alarm_config)
        elif method == "sms":
            await self._send_sms(event, alarm_config)
        elif method == "websocket":
            await self._send_websocket(event, alarm_config)
        elif method == "slack":
            await self._send_slack(event, alarm_config)
        elif method == "webhook":
            await self._send_webhook(event, alarm_config)
        else:
            logger.warning(f"Unknown notification method: {method}")

        # Update throttling counters
        self._last_notification[alarm_config.alarm_id] = datetime.now()
        self._notification_count[alarm_config.alarm_id] += 1

    async def _send_email(self, event: AlarmEvent, alarm_config: AlarmConfig):
        """Send email notification."""
        if not self.config.email_enabled:
            logger.debug("Email notifications disabled")
            return

        if not self.config.smtp_server or not self.config.email_recipients:
            logger.warning("Email configuration incomplete")
            return

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[LabLink Alarm] {event.severity.upper()}: {alarm_config.name}"
            msg['From'] = self.config.email_from or "lablink@example.com"
            msg['To'] = ', '.join(self.config.email_recipients)

            # Create email body
            text_body = self._format_email_text(event, alarm_config)
            html_body = self._format_email_html(event, alarm_config)

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                if self.config.smtp_use_tls:
                    server.starttls()

                if self.config.smtp_username and self.config.smtp_password:
                    server.login(self.config.smtp_username, self.config.smtp_password)

                server.send_message(msg)

            logger.info(f"Email notification sent for alarm {alarm_config.alarm_id}")

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    async def _send_sms(self, event: AlarmEvent, alarm_config: AlarmConfig):
        """Send SMS notification."""
        if not self.config.sms_enabled:
            logger.debug("SMS notifications disabled")
            return

        if not self.config.sms_recipients:
            logger.warning("No SMS recipients configured")
            return

        try:
            # Example using Twilio (requires twilio library)
            if self.config.sms_provider == "twilio":
                await self._send_twilio_sms(event, alarm_config)
            else:
                logger.warning(f"Unsupported SMS provider: {self.config.sms_provider}")

        except Exception as e:
            logger.error(f"Failed to send SMS notification: {e}")

    async def _send_twilio_sms(self, event: AlarmEvent, alarm_config: AlarmConfig):
        """Send SMS via Twilio."""
        try:
            from twilio.rest import Client

            client = Client(self.config.sms_api_key, self.config.sms_api_secret)

            message_body = f"[LabLink {event.severity.upper()}] {alarm_config.name}: {event.message}"

            for recipient in self.config.sms_recipients:
                client.messages.create(
                    body=message_body,
                    from_=self.config.sms_from_number,
                    to=recipient
                )

            logger.info(f"SMS notification sent for alarm {alarm_config.alarm_id}")

        except ImportError:
            logger.error("Twilio library not installed. Install with: pip install twilio")
        except Exception as e:
            logger.error(f"Failed to send Twilio SMS: {e}")

    async def _send_websocket(self, event: AlarmEvent, alarm_config: AlarmConfig):
        """Send WebSocket notification."""
        if not self.config.websocket_enabled:
            logger.debug("WebSocket notifications disabled")
            return

        try:
            from websocket_server import stream_manager

            message = {
                "type": "alarm",
                "severity": event.severity,
                "event_id": event.event_id,
                "alarm_id": event.alarm_id,
                "alarm_name": alarm_config.name,
                "message": event.message,
                "equipment_id": event.equipment_id,
                "parameter": event.parameter,
                "value": event.value,
                "threshold": event.threshold,
                "triggered_at": event.triggered_at.isoformat(),
                "state": event.state
            }

            await stream_manager.broadcast(message)

            logger.info(f"WebSocket notification sent for alarm {alarm_config.alarm_id}")

        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")

    async def _send_slack(self, event: AlarmEvent, alarm_config: AlarmConfig):
        """Send Slack notification."""
        if not hasattr(self.config, 'slack_enabled') or not self.config.slack_enabled:
            logger.debug("Slack notifications disabled")
            return

        if not hasattr(self.config, 'slack_webhook_url') or not self.config.slack_webhook_url:
            logger.warning("Slack webhook URL not configured")
            return

        try:
            import aiohttp

            # Severity emojis and colors
            severity_config = {
                "info": {"emoji": ":information_source:", "color": "#2196F3"},
                "warning": {"emoji": ":warning:", "color": "#FF9800"},
                "error": {"emoji": ":x:", "color": "#F44336"},
                "critical": {"emoji": ":rotating_light:", "color": "#9C27B0"}
            }

            config = severity_config.get(event.severity, {"emoji": ":bell:", "color": "#666"})

            # Create Slack message
            message = {
                "username": "LabLink Alarms",
                "icon_emoji": ":microscope:",
                "attachments": [
                    {
                        "color": config["color"],
                        "title": f"{config['emoji']} {event.severity.upper()}: {alarm_config.name}",
                        "text": event.message,
                        "fields": [
                            {
                                "title": "Equipment",
                                "value": event.equipment_id or "System",
                                "short": True
                            },
                            {
                                "title": "Parameter",
                                "value": event.parameter,
                                "short": True
                            },
                            {
                                "title": "Current Value",
                                "value": str(event.value),
                                "short": True
                            },
                            {
                                "title": "Threshold",
                                "value": str(event.threshold),
                                "short": True
                            }
                        ],
                        "footer": "LabLink Server",
                        "ts": int(event.triggered_at.timestamp())
                    }
                ]
            }

            # Send to Slack
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.slack_webhook_url,
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Slack API returned status {response.status}")
                    else:
                        logger.info(f"Slack notification sent for alarm {alarm_config.alarm_id}")

        except ImportError:
            logger.error("aiohttp library not installed - required for Slack notifications")
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")

    async def _send_webhook(self, event: AlarmEvent, alarm_config: AlarmConfig):
        """Send generic webhook notification."""
        if not hasattr(self.config, 'webhook_enabled') or not self.config.webhook_enabled:
            logger.debug("Webhook notifications disabled")
            return

        if not hasattr(self.config, 'webhook_url') or not self.config.webhook_url:
            logger.warning("Webhook URL not configured")
            return

        try:
            import aiohttp

            # Create webhook payload
            payload = {
                "event_type": "alarm",
                "event_id": event.event_id,
                "alarm_id": event.alarm_id,
                "alarm_name": alarm_config.name,
                "severity": event.severity,
                "state": event.state,
                "message": event.message,
                "equipment_id": event.equipment_id,
                "parameter": event.parameter,
                "value": event.value,
                "threshold": event.threshold,
                "triggered_at": event.triggered_at.isoformat(),
                "description": alarm_config.description
            }

            # Optional webhook authentication
            headers = {"Content-Type": "application/json"}
            if hasattr(self.config, 'webhook_auth_token') and self.config.webhook_auth_token:
                headers["Authorization"] = f"Bearer {self.config.webhook_auth_token}"

            # Send webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status not in [200, 201, 202, 204]:
                        logger.error(f"Webhook returned status {response.status}")
                    else:
                        logger.info(f"Webhook notification sent for alarm {alarm_config.alarm_id}")

        except ImportError:
            logger.error("aiohttp library not installed - required for webhook notifications")
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")

    def _should_send(self, alarm_id: str) -> bool:
        """Check if notification should be sent based on throttling rules."""
        now = datetime.now()

        # Check minimum time between notifications
        last_sent = self._last_notification[alarm_id]
        if (now - last_sent) < timedelta(minutes=self.config.throttle_minutes):
            return False

        # Check maximum notifications per hour
        hour_ago = now - timedelta(hours=1)
        if self._last_notification[alarm_id] > hour_ago:
            if self._notification_count[alarm_id] >= self.config.max_notifications_per_hour:
                return False

        # Reset count if more than an hour has passed
        if self._last_notification[alarm_id] < hour_ago:
            self._notification_count[alarm_id] = 0

        return True

    def _format_email_text(self, event: AlarmEvent, alarm_config: AlarmConfig) -> str:
        """Format plain text email body."""
        lines = [
            f"LabLink Alarm Notification",
            f"=" * 50,
            f"",
            f"Severity: {event.severity.upper()}",
            f"Alarm: {alarm_config.name}",
            f"Description: {alarm_config.description or 'N/A'}",
            f"",
            f"Event Details:",
            f"  Equipment: {event.equipment_id or 'System'}",
            f"  Parameter: {event.parameter}",
            f"  Current Value: {event.value}",
            f"  Threshold: {event.threshold}",
            f"  Message: {event.message}",
            f"",
            f"Triggered At: {event.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Event ID: {event.event_id}",
            f"",
            f"Please acknowledge this alarm in the LabLink interface.",
        ]

        return "\n".join(lines)

    def _format_email_html(self, event: AlarmEvent, alarm_config: AlarmConfig) -> str:
        """Format HTML email body."""
        severity_colors = {
            "info": "#2196F3",
            "warning": "#FF9800",
            "error": "#F44336",
            "critical": "#9C27B0"
        }

        color = severity_colors.get(event.severity, "#666")

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-radius: 0 0 5px 5px; }}
                .detail {{ margin: 10px 0; }}
                .label {{ font-weight: bold; color: #333; }}
                .value {{ color: #666; }}
                .footer {{ margin-top: 20px; color: #999; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>LabLink Alarm Notification</h2>
                    <p>Severity: {event.severity.upper()}</p>
                </div>
                <div class="content">
                    <h3>{alarm_config.name}</h3>
                    <p>{alarm_config.description or ''}</p>

                    <div class="detail">
                        <span class="label">Equipment:</span>
                        <span class="value">{event.equipment_id or 'System'}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Parameter:</span>
                        <span class="value">{event.parameter}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Current Value:</span>
                        <span class="value">{event.value}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Threshold:</span>
                        <span class="value">{event.threshold}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Message:</span>
                        <span class="value">{event.message}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Triggered At:</span>
                        <span class="value">{event.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Event ID:</span>
                        <span class="value">{event.event_id}</span>
                    </div>

                    <p class="footer">
                        Please acknowledge this alarm in the LabLink interface.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return html


# Global notification manager instance
notification_manager = NotificationManager()
