import logging
from typing import Dict, Any, Callable
import asyncio

from app.bot.arni_bot import ArniBot
from app.utils.daily import create_room, create_meeting_token

logger = logging.getLogger(__name__)

class BotManager:
    def __init__(self):
        # meeting_id -> ArniBot instance
        self.active_bots: Dict[str, ArniBot] = {}

    async def start_bot_for_meeting(self, meeting_id: str, room_url: str, broadcast_callback: Callable, wake_word_callback: Callable = None):
        if meeting_id in self.active_bots:
            logger.info(f"Bot already active for meeting {meeting_id}")
            return
            
        try:
            # Generate a bot token (is_owner=True or just a normal token)
            token = await create_meeting_token(room_name=room_url.split('/')[-1], user_name="Arni Bot", user_id="arni-bot", is_owner=False)
            
            bot = ArniBot(
                meeting_id=meeting_id,
                room_url=room_url,
                token=token,
                broadcast_callback=broadcast_callback,
                wake_word_callback=wake_word_callback,
            )
            
            self.active_bots[meeting_id] = bot
            
            # We don't block on join, just run it
            asyncio.create_task(bot.join())
            
            logger.info(f"Successfully started bot for meeting {meeting_id}")
        except Exception as e:
            logger.error(f"Failed to start bot for {meeting_id}: {e}")

    async def stop_bot_for_meeting(self, meeting_id: str):
        bot = self.active_bots.get(meeting_id)
        if bot:
            await bot.leave()
            del self.active_bots[meeting_id]
            logger.info(f"Stopped bot for meeting {meeting_id}")

# Singleton instance
bot_manager = BotManager()
