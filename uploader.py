import asyncio
from pathlib import Path
from typing import Optional, Callable
import logging
from telegram import Bot, InputFile
from telegram.constants import ParseMode
from telegram.error import TimedOut, RetryAfter, NetworkError

from utils import ProgressTracker, format_size, format_speed, logger
from config import CHUNK_SIZE, MAX_CONCURRENT_UPLOADS, MAX_RETRIES, API_ID, API_HASH, BOT_TOKEN
import time

class TelegramUploader:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.upload_limiter = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
        self.max_retries = MAX_RETRIES
        self.pyrogram_app = None
        self._is_started = False
        
        if API_ID and API_HASH:
            try:
                from pyrogram import Client
                # Persistent sessions untuk menyimpan peer cache (Peer id invalid fix)
                self.pyrogram_app = Client(
                    "fast_uploader",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    bot_token=BOT_TOKEN,
                    workers=8  # Meningkatkan concurrency internal
                )
                logger.info("🚀 Pyrogram client initialized for persistent sessions.")
            except ImportError:
                logger.warning("Pyrogram is not installed. Defaulting to standard upload.")

    async def start(self):
        """Start the pyrogram client if it exists"""
        if self.pyrogram_app and not self._is_started:
            try:
                await self.pyrogram_app.start()
                self._is_started = True
                logger.info("✅ Pyrogram client started and connected.")
            except Exception as e:
                logger.error(f"❌ Failed to start Pyrogram: {e}")

    async def stop(self):
        """Stop the pyrogram client gracefully"""
        if self.pyrogram_app and self._is_started:
            try:
                await self.pyrogram_app.stop()
                self._is_started = False
                logger.info("👋 Pyrogram client stopped.")
            except Exception as e:
                logger.error(f"Error stopping Pyrogram: {e}")
        
    async def upload_video(self, file_path: Path, chat_id: int, title: str, episode: str,
                          progress_callback: Optional[Callable] = None,
                          reply_markup=None, message_thread_id: Optional[int] = None) -> bool:
        """Upload video to Telegram with progress tracking and retry"""
        for attempt in range(self.max_retries):
            try:
                async with self.upload_limiter:
                    file_size = file_path.stat().st_size
                    logger.info(f"Starting upload: {file_path} ({format_size(file_size)}) - Attempt {attempt + 1}")
                    
                    if file_size > 2 * 1024 * 1024 * 1024:
                        logger.error(f"File too large: {file_size} bytes")
                        return False
                    
                    # ── Pyrogram Logic ──────────────────────────────────────────
                    if self.pyrogram_app:
                        # Pastikan sudah terhubung
                        if not self._is_started:
                            await self.start()
                            
                        try:
                            # Resolve Peer (Fix: Peer id invalid)
                            # Ini memastikan Pyrogram mengenali chat_id sebelum upload
                            logger.debug(f"Resolving peer for chat {chat_id}...")
                            await self.pyrogram_app.get_chat(chat_id)
                            
                            last_update = [0]
                            async def pyrogram_progress(current, total):
                                now = time.time()
                                if now - last_update[0] > 2.0 or current == total:
                                    last_update[0] = now
                                    if progress_callback:
                                        try:
                                            await progress_callback(current, total)
                                        except Exception:
                                            pass
                                            
                            caption = f"🎬 **{title}**\n"
                            if episode:
                                caption += f"📺 Episode: {episode}\n"
                                
                            pyro_markup = None
                            if reply_markup:
                                try:
                                    from pyrogram.types import InlineKeyboardMarkup as PyroMarkup
                                    from pyrogram.types import InlineKeyboardButton as PyroButton
                                    pyro_buttons = []
                                    for row in reply_markup.inline_keyboard:
                                        pyro_row = []
                                        for btn in row:
                                            if btn.url:
                                                pyro_row.append(PyroButton(btn.text, url=btn.url))
                                            elif btn.callback_data:
                                                pyro_row.append(PyroButton(btn.text, callback_data=btn.callback_data))
                                        pyro_buttons.append(pyro_row)
                                    pyro_markup = PyroMarkup(pyro_buttons)
                                except Exception:
                                    pyro_markup = None

                            is_mkv = file_path.suffix.lower() == ".mkv"
                            target_thread = message_thread_id if message_thread_id else None
                            
                            # Arguments untuk kompatibilitas versi
                            upload_args = {
                                "chat_id": chat_id,
                                "caption": caption,
                                "progress": pyrogram_progress,
                                "reply_markup": pyro_markup
                            }
                            
                            if target_thread:
                                upload_args["message_thread_id"] = target_thread
                            
                            if is_mkv:
                                upload_args["document"] = str(file_path)
                                upload_args["force_document"] = True
                                try:
                                    await self.pyrogram_app.send_document(**upload_args)
                                except TypeError as te:
                                    if "message_thread_id" in str(te):
                                        upload_args.pop("message_thread_id")
                                        upload_args["reply_to_message_id"] = target_thread
                                        await self.pyrogram_app.send_document(**upload_args)
                                    else: raise te
                            else:
                                upload_args["video"] = str(file_path)
                                try:
                                    await self.pyrogram_app.send_video(**upload_args)
                                except TypeError as te:
                                    if "message_thread_id" in str(te):
                                        upload_args.pop("message_thread_id")
                                        upload_args["reply_to_message_id"] = target_thread
                                        await self.pyrogram_app.send_video(**upload_args)
                                    else: raise te
                                    
                            logger.info(f"🚀 Pyrogram Upload completed for {file_path}")
                            return True
                            
                        except Exception as pyro_err:
                            logger.error(f"⚠️ Pyrogram upload failed, trying fallback: {pyro_err}")
                            # Lanjut ke fallback standard uploader di bawah
                    
                    # ── Standard Uploader Fallback (python-telegram-bot) ──────
                    tracker = ProgressTracker(file_size, progress_callback)
                    await tracker.start()
                    
                    is_mkv = file_path.suffix.lower() == ".mkv"
                    with open(file_path, 'rb') as video_file:
                        caption = f"🎬 <b>{title}</b>\n"
                        if episode:
                            caption += f"📺 Episode: {episode}\n"
                        
                        if is_mkv:
                            await self.bot.send_document(
                                chat_id=chat_id,
                                document=InputFile(video_file, filename=file_path.name),
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                reply_markup=reply_markup,
                                message_thread_id=message_thread_id
                            )
                        else:
                            await self.bot.send_video(
                                chat_id=chat_id,
                                video=InputFile(video_file, filename=file_path.name),
                                caption=caption,
                                supports_streaming=True,
                                parse_mode=ParseMode.HTML,
                                reply_markup=reply_markup,
                                message_thread_id=message_thread_id
                            )
                    return True
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(5)
                else:
                    return False
        return False
    
    async def update_message(self, chat_id: int, message_id: int, text: str, reply_markup=None, message_thread_id: Optional[int] = None):
        """Edit or Resend message if not found (Smart Resend)"""
        for attempt in range(self.max_retries):
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=text,
                    parse_mode=ParseMode.HTML, reply_markup=reply_markup
                )
                return
            except Exception as e:
                error_str = str(e).lower()
                # Jika pesan hilang (404) atau tidak bisa diedit, kirim pesan baru (Smart Resend)
                if any(x in error_str for x in ["not found", "message can't be found", "can't be edited"]):
                    try:
                        return await self.bot.send_message(
                            chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, 
                            reply_markup=reply_markup, message_thread_id=message_thread_id
                        )
                    except: return
                
                # Jika pesan adalah foto (caption)
                if "no text" in error_str or "can't be edited" in error_str:
                    try:
                        await self.bot.edit_message_caption(
                            chat_id=chat_id, message_id=message_id, caption=text,
                            parse_mode=ParseMode.HTML, reply_markup=reply_markup
                        )
                        return
                    except: pass

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    if "not modified" not in error_str:
                        logger.warning(f"Failed to update message: {e}")