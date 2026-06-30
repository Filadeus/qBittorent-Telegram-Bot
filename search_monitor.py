from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import logger
import database
from qbit_client import QBitClientWrapper
from utils import format_size

async def check_search_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job that runs search queries for favorites and notifies users of new hits."""
    logger.info("Executing periodic search alert checks...")
    
    # 1. Fetch all favorite terms from DB
    favorites = database.get_favorites()
    if not favorites:
        logger.info("No favorite search terms registered. Skipping checks.")
        return

    # 2. Instantiate and connect qBittorrent client
    try:
        qbt = QBitClientWrapper()
        qbt.connect()
    except Exception as e:
        logger.error(f"Search monitor failed to connect to qBittorrent: {e}")
        return

    # 3. Process each favorite search query
    for fav in favorites:
        term = fav['search_term']
        chat_id = fav['chat_id']
        logger.info(f"Checking search alerts for favorite term: '{term}'")

        try:
            # Get top hits from qBittorrent search engine
            results = qbt.search_torrents(term, limit=10, timeout=10)
            if not results:
                logger.debug(f"No search results returned for '{term}'")
                continue

            for res in results:
                file_url = res.get('fileUrl')
                file_name = res.get('fileName')
                
                if not file_url or not file_name:
                    continue

                # If this result hasn't been notified for this search term yet
                if not database.is_hit_notified(term, file_url):
                    # Cache the file URL to bypass Telegram's 64-byte callback_data limit
                    cache_id = database.cache_search_result(file_url, file_name)
                    
                    size_bytes = res.get('fileSize', 0)
                    seeds = res.get('nbSeeders', 0)
                    leechs = res.get('nbLeechers', 0)
                    site_url = res.get('siteUrl', 'Unknown')
                    
                    formatted_size = format_size(size_bytes)
                    
                    # Escape text for Markdown if needed, but simple clean formatting is usually fine.
                    # Standard markdown escape isn't strictly necessary if we format cleanly.
                    message = (
                        f"🔔 *New Search Hit for '{term}'*\n\n"
                        f"📁 *Name*: {file_name}\n"
                        f"💾 *Size*: {formatted_size}\n"
                        f"🌱 *Seeders*: {seeds} | 📥 *Leechers*: {leechs}\n"
                        f"🔌 *Source*: {site_url}\n"
                    )

                    keyboard = [
                        [InlineKeyboardButton("📥 Download Torrent", callback_data=f"dl_hit:{cache_id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                        # Mark as notified to prevent spamming
                        database.add_notified_hit(term, file_url)
                        logger.info(f"Notified chat {chat_id} of new hit: '{file_name}'")
                    except Exception as msg_ex:
                        logger.error(f"Failed to send Telegram notification to chat {chat_id}: {msg_ex}")

        except Exception as term_ex:
            logger.error(f"Error processing favorite search '{term}': {term_ex}")

    # Clean up SQLite search cache older than 24 hours to keep the DB small
    try:
        database.cleanup_old_cache(hours=24)
        logger.debug("Database search cache cleaned up.")
    except Exception as cleanup_ex:
        logger.error(f"Failed to clean up search cache: {cleanup_ex}")
