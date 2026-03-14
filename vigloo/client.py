import aiohttp
import logging
from typing import Dict, Any, List, Optional
from config import DOWNLOAD_PROXY

logger = logging.getLogger(__name__)

class ViglooClient:
    BASE_URL = "https://captain.sapimu.au/vigloo/api/v1"
    
    def __init__(self, token: str, proxy: Optional[str] = None):
        self.token = token
        self.proxy = proxy or DOWNLOAD_PROXY
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params, proxy=self.proxy) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.error(f"Vigloo API error {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.error(f"Vigloo request failed: {e}")
            return None

    async def get_drama_detail(self, drama_id: str, lang: str = "en") -> Optional[Dict[str, Any]]:
        """GET /api/v1/drama/:id"""
        return await self._get(f"/drama/{drama_id}", params={"lang": lang})

    async def get_episodes(self, program_id: str, season_id: str, lang: str = "en") -> Optional[Dict[str, Any]]:
        """GET /api/v1/drama/:programId/season/:seasonId/episodes"""
        return await self._get(f"/drama/{program_id}/season/{season_id}/episodes", params={"lang": lang})

    async def get_play_info(self, season_id: str, ep: int) -> Optional[Dict[str, Any]]:
        """GET /api/v1/play"""
        return await self._get("/play", params={"seasonId": season_id, "ep": ep})

    async def get_stream_url(self, season_id: str, ep: int) -> Optional[str]:
        """GET /api/v1/stream"""
        # Based on the user request, this returns HLS stream with embedded cookies
        # But we might need the actual URL from the JSON response
        data = await self._get("/stream", params={"seasonId": season_id, "ep": ep})
        if data and data.get("status") == "OK":
            payload = data.get("payload")
            if isinstance(payload, dict):
                return payload.get("url")
        return None
