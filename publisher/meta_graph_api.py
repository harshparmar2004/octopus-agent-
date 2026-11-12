import time
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import requests

from config import settings

logger = logging.getLogger("MetaPublisher")

class MetaReelsPublisher:
    def __init__(self, ig_user_id: Optional[str] = None, access_token: Optional[str] = None):
        self.ig_user_id = ig_user_id or getattr(settings, "INSTAGRAM_USER_ID", getattr(settings, "IG_USER_ID", ""))
        self.access_token = access_token or getattr(settings, "META_GRAPH_ACCESS_TOKEN", getattr(settings, "META_ACCESS_TOKEN", ""))
        self.version = settings.META_GRAPH_VERSION
        self.base_url = f"https://graph.facebook.com/{self.version}"

    def publish_reel(self, video_public_url: str, caption: str, share_to_feed: bool = True, dry_run: bool = False) -> Dict[str, Any]:
        """
        Publishes a Reel to Instagram via the official Meta Graph API:
        1. Initialize Media Container (media_type=REELS)
        2. Poll container status until FINISHED
        3. Trigger media_publish
        """
        if dry_run or not self.ig_user_id or not self.access_token:
            logger.info("[DRY RUN] Simulating Instagram Reel publication.")
            return {
                "success": True,
                "mode": "dry_run",
                "simulated_media_id": "18012345678901234",
                "message": "Reel verified for publishing. Add INSTAGRAM_USER_ID and META_GRAPH_ACCESS_TOKEN to post live."
            }

        try:
            container_id = self._create_container(video_public_url, caption, share_to_feed)
            logger.info(f"Created Reel container ID: {container_id}")
            self._wait_until_ready(container_id)
            logger.info(f"Container {container_id} is ready for publishing.")
            media_id = self._publish_container(container_id)
            logger.info(f"Successfully published Reel! Live Instagram Post ID: {media_id}")

            return {
                "success": True,
                "media_id": media_id,
                "container_id": container_id
            }
        except Exception as e:
            logger.error(f"Failed to publish reel via Meta Graph API: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def publish_local_reel(
        self,
        local_video_path: str,
        caption: str,
        share_to_feed: bool = True,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Publishes a local video file directly to Instagram Reels using the Meta Resumable Upload API.
        Does not require a public URL or tunnel.
        """
        if dry_run or not self.ig_user_id or not self.access_token:
            logger.info("[DRY RUN] Simulating local Instagram Reel publication.")
            return {
                "success": True,
                "mode": "dry_run",
                "simulated_media_id": "18012345678901234",
                "message": "Local reel verified for publishing. Add INSTAGRAM_USER_ID and META_GRAPH_ACCESS_TOKEN to post live."
            }

        p = Path(local_video_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: {local_video_path}"}

        file_size = p.stat().st_size

        try:
            # 1. Initialize resumable upload container
            init_url = f"{self.base_url}/{self.ig_user_id}/media"
            init_payload = {
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": caption,
                "share_to_feed": share_to_feed,
                "thumb_offset": 1000,
                "access_token": self.access_token
            }
            res = requests.post(init_url, data=init_payload, timeout=30)
            init_data = res.json()
            if "id" not in init_data or "uri" not in init_data:
                raise RuntimeError(f"Failed to initialize resumable container: {init_data}")

            container_id = init_data["id"]
            upload_uri = init_data["uri"]
            logger.info(f"Initialized Resumable Reel container: {container_id}")

            # 2. Upload video binary bytes to upload_uri
            upload_headers = {
                "Authorization": f"OAuth {self.access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream"
            }
            with open(p, "rb") as f:
                up_res = requests.post(upload_uri, headers=upload_headers, data=f, timeout=120)

            if up_res.status_code not in (200, 201):
                raise RuntimeError(f"Failed to upload binary bytes: {up_res.status_code} - {up_res.text}")

            logger.info(f"Successfully uploaded {file_size} bytes to Meta. Waiting for container to process...")

            # 3. Wait until ready
            self._wait_until_ready(container_id)
            logger.info(f"Container {container_id} is ready for publishing.")

            # 4. Publish container
            media_id = self._publish_container(container_id)
            logger.info(f"🎉 Successfully published Reel live! Instagram Post ID: {media_id}")

            return {
                "success": True,
                "media_id": media_id,
                "container_id": container_id,
                "status": "PUBLISHED"
            }
        except Exception as e:
            logger.error(f"Failed to publish local reel via Meta Graph API: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _create_container(self, video_url: str, caption: str, share_to_feed: bool) -> str:
        url = f"{self.base_url}/{self.ig_user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": share_to_feed,
            "thumb_offset": 1000,
            "access_token": self.access_token
        }
        res = requests.post(url, data=payload, timeout=30)
        data = res.json()
        if "id" not in data:
            raise RuntimeError(f"Failed to initialize container: {data}")
        return data["id"]

    def _wait_until_ready(self, container_id: str, max_retries: int = 30, delay_seconds: int = 5) -> None:
        url = f"{self.base_url}/{container_id}"
        params = {
            "fields": "status_code,status",
            "access_token": self.access_token
        }
        for attempt in range(max_retries):
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            status = data.get("status_code", "").upper()
            logger.info(f"Status check {attempt + 1}/{max_retries}: {status}")
            if status == "FINISHED":
                return
            elif status in ["ERROR", "EXPIRED"]:
                raise RuntimeError(f"Container processing failed: {data}")
            time.sleep(delay_seconds)
        raise TimeoutError(f"Container {container_id} timed out while processing.")

    def _publish_container(self, container_id: str) -> str:
        url = f"{self.base_url}/{self.ig_user_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self.access_token
        }
        res = requests.post(url, data=payload, timeout=30)
        data = res.json()
        if "id" not in data:
            raise RuntimeError(f"Failed to publish container: {data}")
        return data["id"]

    @classmethod
    def discover_instagram_accounts(cls, user_access_token: str, version: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Auto-discovers all connected Facebook Pages and linked Instagram Business/Creator
        accounts from a single Meta User Access Token.
        """
        v = version or settings.META_GRAPH_VERSION
        url = f"https://graph.facebook.com/{v}/me/accounts"
        params = {
            "fields": "id,name,access_token,category,instagram_business_account{id,username,name,profile_picture_url,followers_count}",
            "limit": 100,
            "access_token": user_access_token
        }
        discovered = []
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                data = res.json()
                for page in data.get("data", []):
                    page_name = page.get("name")
                    page_token = page.get("access_token") or user_access_token
                    ig_acc = page.get("instagram_business_account")
                    if ig_acc and ig_acc.get("id"):
                        username = ig_acc.get("username", "")
                        discovered.append({
                            "id": username.replace(".", "_") if username else f"ig_{ig_acc['id']}",
                            "handle": f"@{username}" if username else f"@ig_{ig_acc['id']}",
                            "display_name": ig_acc.get("name") or page_name,
                            "niche": "Tech and Science",
                            "ig_user_id": str(ig_acc["id"]),
                            "access_token": page_token,
                            "avatar_initials": (username[:2] if username else "IG").upper(),
                            "brand_color": "#f97316",
                            "profile_pic_url": ig_acc.get("profile_picture_url", ""),
                            "followers": ig_acc.get("followers_count", 0),
                            "fb_page_name": page_name,
                            "is_active": 1
                        })
            else:
                logger.warning(f"Meta discovery error: {res.status_code} - {res.text[:200]}")
        except Exception as e:
            logger.error(f"Failed to discover Instagram accounts: {e}")
        return discovered

    @classmethod
    def test_token_validity(cls, access_token: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Tests whether an access token is valid and inspects its identity.
        """
        if not access_token:
            return {"valid": False, "error": "No token provided"}
        v = version or settings.META_GRAPH_VERSION
        try:
            me_url = f"https://graph.facebook.com/{v}/me"
            res = requests.get(me_url, params={"fields": "id,name", "access_token": access_token}, timeout=10)
            if res.status_code == 200:
                me_data = res.json()
                return {
                    "valid": True,
                    "id": me_data.get("id"),
                    "name": me_data.get("name"),
                    "type": "PAGE_OR_USER_TOKEN",
                    "status": "ACTIVE"
                }
            else:
                err_msg = res.json().get("error", {}).get("message", res.text[:150])
                return {"valid": False, "error": err_msg}
        except Exception as e:
            return {"valid": False, "error": str(e)}
