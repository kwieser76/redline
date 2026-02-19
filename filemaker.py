"""
FileMaker REST API integration.

This module provides a thin wrapper around the FileMaker Data API.
In POC mode (when FILEMAKER_HOST is not configured) every call is a no-op
that logs what would have been sent.

FileMaker Data API reference:
  https://help.claris.com/en/data-api-guide/
"""
import logging
from typing import Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


class FileMakerClient:
    """Minimal FileMaker Data API client."""

    def __init__(self) -> None:
        self.host = Config.FILEMAKER_HOST
        self.database = Config.FILEMAKER_DATABASE
        self.username = Config.FILEMAKER_USERNAME
        self.password = Config.FILEMAKER_PASSWORD
        self._token: Optional[str] = None

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _base_url(self) -> str:
        return f"{self.host}/fmi/data/v2/databases/{self.database}"

    def _login(self) -> bool:
        """Obtain a session token from FileMaker."""
        if not self.password:
            logger.warning("FileMaker password not configured – skipping login.")
            return False
        try:
            resp = requests.post(
                f"{self._base_url()}/sessions",
                auth=(self.username, self.password),
                headers={"Content-Type": "application/json"},
                json={},
                timeout=10,
            )
            resp.raise_for_status()
            self._token = resp.json()["response"]["token"]
            return True
        except Exception as exc:
            logger.error("FileMaker login failed: %s", exc)
            return False

    def _logout(self) -> None:
        if not self._token:
            return
        try:
            requests.delete(
                f"{self._base_url()}/sessions/{self._token}",
                timeout=10,
            )
        except Exception as exc:
            logger.warning("FileMaker logout error: %s", exc)
        finally:
            self._token = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def update_device_status(self, device_id: str, status: str) -> bool:
        """Set the device status field in FileMaker (e.g. 'Wartung' or 'Verfügbar')."""
        if not self._login():
            logger.info(
                "[POC] Would set FileMaker device %s status → %s", device_id, status
            )
            return True  # graceful degradation in POC mode

        try:
            # Find the record first
            find_resp = requests.post(
                f"{self._base_url()}/layouts/Geräte/_find",
                headers=self._headers(),
                json={"query": [{"Geräte-ID": device_id}]},
                timeout=10,
            )
            find_resp.raise_for_status()
            records = find_resp.json()["response"]["data"]
            if not records:
                logger.warning("Device %s not found in FileMaker.", device_id)
                return False

            record_id = records[0]["recordId"]

            # Patch the status
            patch_resp = requests.patch(
                f"{self._base_url()}/layouts/Geräte/records/{record_id}",
                headers=self._headers(),
                json={"fieldData": {"Status": status}},
                timeout=10,
            )
            patch_resp.raise_for_status()
            logger.info("FileMaker: device %s → %s", device_id, status)
            return True
        except Exception as exc:
            logger.error("FileMaker update_device_status error: %s", exc)
            return False
        finally:
            self._logout()

    def create_defect_record(self, payload: dict) -> bool:
        """Create a defect record in FileMaker's Defekte layout."""
        if not self._login():
            logger.info("[POC] Would create FileMaker defect record: %s", payload)
            return True

        try:
            resp = requests.post(
                f"{self._base_url()}/layouts/Defekte/records",
                headers=self._headers(),
                json={"fieldData": payload},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("FileMaker defect record created: %s", resp.json())
            return True
        except Exception as exc:
            logger.error("FileMaker create_defect_record error: %s", exc)
            return False
        finally:
            self._logout()


# Module-level singleton
fm_client = FileMakerClient()
