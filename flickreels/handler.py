import logging
import json
from pathlib import Path
from typing import Dict, Optional
from telegram import Update
from telegram.ext import ContextTypes
from config import FLICKREELS_JSON_DIR
from flickreels.parser import FlickReelsParser

logger = logging.getLogger(__name__)

class FlickReelsHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def handle_flickreels_json(self, update: Update, context: ContextTypes.DEFAULT_TYPE, json_file_path: Path):
        """
        Process a detected FlickReels JSON file.
        """
        user_id = update.effective_user.id
        
        # Parse the JSON
        data = await FlickReelsParser.parse_json(json_file_path)
        if not data:
            await update.message.reply_text("❌ Invalid FlickReels JSON format.")
            return

        drama = data['drama']
        episodes = data['episodes']
        
        result_episodes = []
        for ep in episodes:
            res_ep = {
                'id': ep['id'],
                'episode': ep['episode'],
                'title': ep['title'],
                'url': ep['url'],
                'drama_title': drama['title'],
                'source': 'dramaflickreels'
            }
            if ep.get('subtitle_url'):
                res_ep['subtitle_url'] = ep['subtitle_url']
                res_ep['subtitle_mode'] = 'embed' # Merge using ffmpeg
            
            result_episodes.append(res_ep)
        
        # Save to flickreels/json/
        safe_title = "".join([c if c.isalnum() else "_" for c in drama['title']])
        flick_json_path = FLICKREELS_JSON_DIR / f"{safe_title}_{user_id}.json"
        
        with open(flick_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        # Store in user_data for the bot's standard download flow
        context.user_data['drama_info'] = drama
        context.user_data['episodes'] = episodes
        context.user_data['drama_title'] = drama['title']
        context.user_data['json_path'] = str(flick_json_path)
        context.user_data['source'] = 'dramaflickreels'

        # Show info and ask for choice using the bot's existing confirm_batch method
        # Display drama info per specification
        info_text = (
            f"🎬 <b>Title:</b> {drama.get('title')}\n"
            f"🧾 <b>Description:</b> {drama.get('description')}\n"
            f"📺 <b>Total Episodes:</b> {drama.get('chapterCount')}\n"
            f"🖼 <b>Cover Image:</b> {drama.get('cover')}\n\n"
            f"<i>Silakan pilih menu di bawah:</i>"
        )
        
        # Use inline buttons for final specification
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton("📦 Download All Episodes", callback_data="flick_all")],
            [InlineKeyboardButton("🎬 Download Episode", callback_data="flick_select")],
            [InlineKeyboardButton("❌ Cancel", callback_data="flick_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(info_text, reply_markup=reply_markup, parse_mode="HTML")
        from bot import AWAITING_BATCH_CHOICE
        return AWAITING_BATCH_CHOICE
