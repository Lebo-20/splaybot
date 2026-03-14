import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class FlickReelsParser:
    @staticmethod
    async def parse_json(file_path: Path) -> Optional[Dict]:
        """
        Parse and validate FlickReels JSON format.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate source
            source = data.get('drama', {}).get('source', '')
            if source != "dramaflickreels":
                return None
            
            drama = data.get('drama', {})
            episodes_raw = data.get('episodes', [])
            
            # Extract basic info
            drama_info = {
                'title': drama.get('title', 'Unknown Title'),
                'cover': drama.get('cover', ''),
                'description': drama.get('description', ''),
                'chapterCount': drama.get('total_chapters') or drama.get('chapterCount', 0),
                'source': source
            }
            
            episodes = []
            for ep in episodes_raw:
                # FlickReels specific nesting
                raw_data = ep.get('raw', {})
                video_url = raw_data.get('videoUrl')
                
                if not video_url:
                    continue
                    
                # Extract subtitles
                subtitle_url = None
                subtitles = raw_data.get('subtiles', [])
                if isinstance(subtitles, list):
                    for sub in subtitles:
                        if sub.get('language') == 'Indonesian':
                            subtitle_url = sub.get('url')
                            break

                episodes.append({
                    'id': ep.get('id'),
                    'episode': str(ep.get('index', 0) + 1), # index starts at 0
                    'title': ep.get('name', f"EP {ep.get('index', 0) + 1}"),
                    'url': video_url,
                    'subtitle_url': subtitle_url,
                    'is_lock': ep.get('unlock', True) == False
                })
            
            if not episodes:
                logger.warning("FlickReels JSON has no valid episodes with videoUrl")
                return None
                
            return {
                'drama': drama_info,
                'episodes': episodes
            }
            
        except Exception as e:
            logger.error(f"Error parsing FlickReels JSON: {e}")
            return None
