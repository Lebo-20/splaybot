import json
import logging
from typing import Dict, Any, List, Optional
from .client import ViglooClient
from config import VIGLOO_TOKEN

logger = logging.getLogger(__name__)

class ViglooParser:
    def __init__(self, token: Optional[str] = None):
        self.token = token or VIGLOO_TOKEN
        self.client = ViglooClient(self.token)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Vigloo JSON format.
        Supports:
        - Episode list (payloads array)
        - Single episode (payload object)
        """
        result = {
            "title": data.get("title") or "Vigloo Video",
            "episodes": [],
            "cover": data.get("cover"),
            "source": "vigloo"
        }

        # Check for episode list
        payloads = data.get("payloads")
        if isinstance(payloads, list):
            for ep in payloads:
                ep_num = str(ep.get("episodeNumber", ""))
                season_id = str(ep.get("seasonId", ""))
                
                result["episodes"].append({
                    "episode": ep_num,
                    "season_id": season_id,
                    "title": result["title"],
                    "id": ep.get("id"),
                    "url": None, # Needs to be fetched via client
                    "subtitle_url": None,
                    "source": "vigloo"
                })
        
        # Check for single episode payload
        payload = data.get("payload")
        if isinstance(payload, dict):
            sub_url = None
            subtitles = payload.get("subtitles", [])
            if subtitles:
                indo_sub = next((s for s in subtitles if s.get("lang") == "id"), subtitles[0])
                sub_url = indo_sub.get("url")

            # If it already has a URL (legacy or direct result)
            if "url" in payload:
                result["episodes"].append({
                    "episode": str(payload.get("episodeNumber", "1")),
                    "title": result["title"],
                    "url": payload["url"],
                    "subtitle_url": sub_url,
                    "source": "vigloo"
                })
            else:
                # Single episode without URL
                result["episodes"].append({
                    "episode": str(payload.get("episodeNumber", "1")),
                    "season_id": str(payload.get("seasonId", "")),
                    "title": result["title"],
                    "id": payload.get("id"),
                    "url": None,
                    "subtitle_url": sub_url,
                    "source": "vigloo"
                })

        return result

    async def fill_urls(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fetch stream URLs for episodes that don't have them.
        """
        for ep in episodes:
            if ep.get("season_id") and ep.get("episode") is not None:
                try:
                    ep_num = int(ep["episode"])
                    
                    # 1. Get play info for subtitles
                    play_info = await self.client.get_play_info(ep["season_id"], ep_num)
                    if play_info and play_info.get("status") == "OK":
                        payload = play_info.get("payload")
                        if isinstance(payload, dict):
                            subtitles = payload.get("subtitles", [])
                            # Priority for Indonesian ('id')
                            indo_sub = next((s for s in subtitles if s.get("lang") == "id"), None)
                            if indo_sub:
                                ep["subtitle_url"] = indo_sub.get("url")
                                logger.info(f"Found Indonesian subtitle for ep {ep_num}")
                            elif subtitles:
                                # Fallback to first available subtitle (usually English)
                                ep["subtitle_url"] = subtitles[0].get("url")
                                logger.info(f"Fallback to {subtitles[0].get('lang')} subtitle for ep {ep_num}")

                    # 2. Get stream URL if not already present
                    if not ep.get("url"):
                        url = await self.client.get_stream_url(ep["season_id"], ep_num)
                        if url:
                            ep["url"] = url
                            logger.info(f"Fetched Vigloo URL for ep {ep_num}: {url[:50]}...")
                except Exception as e:
                    logger.error(f"Failed to fetch Vigloo data for ep {ep.get('episode')}: {e}")
        return episodes
