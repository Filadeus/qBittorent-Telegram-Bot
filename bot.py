import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

from config import Config, logger
import database
from qbit_client import QBitClientWrapper
from search_monitor import check_search_alerts
from utils import format_size, format_speed, format_eta, get_progress_bar

# --- Security Decorator ---

def auth_guard(func):
    """Enforces that only allowed user IDs can trigger bot commands or callbacks."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id not in Config.ALLOWED_USER_IDS:
            logger.warning(
                f"Access denied for user: {user.id if user else 'Unknown'} "
                f"({user.username if user else 'N/A'})"
            )
            if update.message:
                await update.message.reply_text("⛔ *Unauthorized*: You do not have permission to control this bot.", parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Unauthorized access.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Command Handlers ---

@auth_guard
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and lists available bot commands."""
    # Standard Markdown is easier to read and format without escaping everything.
    # Let's send using Markdown (V1) for compatibility and simplicity.
    help_text_markdown = (
        "🚀 *qBittorrent Bot Controller*\n\n"
        "Welcome! Use the commands below to interact with your instance:\n\n"
        "💾 /storage - Check free storage space and global speeds\n"
        "⚡ /progress - Show and control active torrent downloads\n"
        "🔍 /search <term> - Search torrents using qBittorrent plugins\n"
        "⭐ /favorites - List/manage favorite keywords for automated alerts\n"
        "❓ /help - Show this command reference"
    )
    await update.message.reply_text(help_text_markdown, parse_mode="Markdown")

@auth_guard
async def storage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays storage availability and global download/upload transfer speeds."""
    status_msg = await update.message.reply_text("⏳ Fetching storage details...")
    try:
        qbt = QBitClientWrapper()
        info = qbt.get_storage_info()
        
        free_space = format_size(info['free_bytes'])
        dl_speed = format_speed(info['dl_speed'])
        up_speed = format_speed(info['up_speed'])
        
        msg = (
            "💾 *qBittorrent Storage Info*\n\n"
            f"🟢 *Free Disk Space*: {free_space}\n"
            f"📥 *Global Download Speed*: {dl_speed}\n"
            f"📤 *Global Upload Speed*: {up_speed}"
        )
        await status_msg.edit_text(msg, parse_mode="Markdown")
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to fetch storage information: {e}")

@auth_guard
async def progress_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists current active downloads along with progress and control buttons."""
    status_msg = await update.message.reply_text("⏳ Fetching active downloads...")
    try:
        qbt = QBitClientWrapper()
        active = qbt.get_downloads_progress()
        
        if not active:
            await status_msg.edit_text("⚡ No active downloads at the moment.")
            return
            
        message_lines, keyboard = build_progress_layout(active)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(
            "\n".join(message_lines),
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to fetch downloads progress: {e}")

@auth_guard
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes a search using qBittorrent's engine, returning top 5 hits sorted by seeders."""
    if not context.args:
        await update.message.reply_text("⚠️ Please specify search term(s). Example: `/search Ubuntu`", parse_mode="Markdown")
        return
        
    query_term = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🔍 Searching qBittorrent for: '{query_term}'... Please wait.")
    
    try:
        qbt = QBitClientWrapper()
        results = qbt.search_torrents(query_term, limit=5, timeout=10)
        
        # Save query term in cache to bypass callback length limits in case they click "Add Favorite"
        term_cache_id = database.cache_search_result(file_url="favorite_query", file_name=query_term)
        
        if not results:
            keyboard = [
                [InlineKeyboardButton("⭐ Save Search to Favorites", callback_data=f"fav_add:{term_cache_id}")]
            ]
            await status_msg.edit_text(
                f"🔍 *No results found for '{query_term}'*\n\n"
                f"Verify that your search plugins are active in qBittorrent.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
            
        message_lines = [f"🔍 *Top Results for '{query_term}':*\n"]
        keyboard = []
        
        for idx, res in enumerate(results, 1):
            name = res.get('fileName')
            size_bytes = res.get('fileSize', 0)
            seeds = res.get('nbSeeders', 0)
            leechs = res.get('nbLeechers', 0)
            file_url = res.get('fileUrl')
            
            # Cache the file URL and get a tiny numeric ID
            cache_id = database.cache_search_result(file_url, name)
            
            formatted_size = format_size(size_bytes)
            message_lines.append(
                f"*{idx}.* 📁 {name}\n"
                f"   Size: {formatted_size} | Seeds: {seeds} | Leechs: {leechs}\n"
            )
            keyboard.append([
                InlineKeyboardButton(f"📥 Download {idx}", callback_data=f"dl_hit:{cache_id}")
            ])
            
        keyboard.append([
            InlineKeyboardButton("⭐ Save Search to Favorites", callback_data=f"fav_add:{term_cache_id}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text("\n".join(message_lines), reply_markup=reply_markup, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Search handler failed: {e}")
        await status_msg.edit_text(f"❌ Search failed: {e}")

@auth_guard
async def favorites_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists current search favorites and allows deleting them."""
    favorites = database.get_favorites()
    if not favorites:
        await update.message.reply_text("⭐ No favorite search terms configured. Add them by using `/search <query>`.")
        return
        
    message_lines = ["⭐ *Favorite Search Alerts:*\n"]
    keyboard = []
    
    for f in favorites:
        fav_id = f['id']
        term = f['search_term']
        message_lines.append(f"• *{term}*")
        keyboard.append([
            InlineKeyboardButton(f"❌ Remove '{term}'", callback_data=f"fav_del:{fav_id}")
        ])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("\n".join(message_lines), reply_markup=reply_markup, parse_mode="Markdown")

# --- Layout Helpers ---

def build_progress_layout(active_torrents):
    """Builds the textual list and inline buttons for active downloads."""
    message_lines = ["⚡ *Active Downloads:*\n"]
    keyboard = []
    
    for idx, t in enumerate(active_torrents, 1):
        name = t['name']
        prog_bar = get_progress_bar(t['progress'])
        size = format_size(t['size'])
        speed = format_speed(t['dlspeed'])
        eta = format_eta(t['eta'])
        state = t['state']
        
        state_desc = state
        if state == 'downloading':
            state_desc = "📥 Downloading"
        elif state == 'stalledDL':
            state_desc = "⏳ Stalled"
        elif state == 'checkingDL':
            state_desc = "🔍 Checking"
        elif state == 'pausedDL':
            state_desc = "⏸ Paused"
        elif state == 'metaDL':
            state_desc = "📋 Fetching Metadata"
            
        message_lines.append(
            f"*{idx}.* 📁 {name}\n"
            f"   State: {state_desc}\n"
            f"   Progress: {prog_bar}\n"
            f"   Size: {size} | Speed: {speed} | ETA: {eta}\n"
        )
        
        # Determine correct pause/resume action
        action_btn = InlineKeyboardButton("⏸ Pause", callback_data=f"torrent_pause:{t['hash']}")
        if state in ('pausedDL', 'paused'):
            action_btn = InlineKeyboardButton("▶ Resume", callback_data=f"torrent_resume:{t['hash']}")
            
        delete_btn = InlineKeyboardButton("🗑 Delete", callback_data=f"torrent_delete:{t['hash']}")
        
        keyboard.append([
            InlineKeyboardButton(f"{idx}.", callback_data="noop"),
            action_btn,
            delete_btn
        ])
        
    return message_lines, keyboard

async def refresh_progress_message(message):
    """Refreshes an existing progress list message."""
    try:
        qbt = QBitClientWrapper()
        active = qbt.get_downloads_progress()
        
        if not active:
            await message.edit_text("⚡ No active downloads at the moment.")
            return
            
        message_lines, keyboard = build_progress_layout(active)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text("\n".join(message_lines), reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to refresh progress message: {e}")
        await message.edit_text(f"❌ Failed to refresh progress: {e}")

async def refresh_favorites_message(message):
    """Refreshes an existing favorites list message."""
    favorites = database.get_favorites()
    if not favorites:
        await message.edit_text("⭐ No favorite search terms configured.")
        return
        
    message_lines = ["⭐ *Favorite Search Alerts:*\n"]
    keyboard = []
    
    for f in favorites:
        fav_id = f['id']
        term = f['search_term']
        message_lines.append(f"• *{term}*")
        keyboard.append([
            InlineKeyboardButton(f"❌ Remove '{term}'", callback_data=f"fav_del:{fav_id}")
        ])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.edit_text("\n".join(message_lines), reply_markup=reply_markup, parse_mode="Markdown")

# --- Callback Queries ---

@auth_guard
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all button click events (callbacks)."""
    query = update.callback_query
    await query.answer()  # Acknowledge button click
    
    data = query.data
    
    if data == "noop":
        return
        
    elif data.startswith("torrent_pause:"):
        h = data.split(":", 1)[1]
        try:
            qbt = QBitClientWrapper()
            qbt.pause_torrent(h)
            await refresh_progress_message(query.message)
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to pause torrent: {e}")
            
    elif data.startswith("torrent_resume:"):
        h = data.split(":", 1)[1]
        try:
            qbt = QBitClientWrapper()
            qbt.resume_torrent(h)
            await refresh_progress_message(query.message)
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to resume torrent: {e}")
            
    elif data.startswith("torrent_delete:"):
        h = data.split(":", 1)[1]
        try:
            qbt = QBitClientWrapper()
            torrents = qbt.client.torrents_info(torrent_hashes=h)
            if torrents:
                name = torrents[0].name
                keyboard = [
                    [
                        InlineKeyboardButton("🗑 Torrent Only", callback_data=f"torrent_delconf:{h}"),
                        InlineKeyboardButton("🔥 Torrent & Files", callback_data=f"torrent_delfiles:{h}")
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="torrent_cancel")]
                ]
                await query.edit_message_text(
                    text=f"⚠️ *Delete confirmation needed*\n\n📁 *Name*: {name}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Torrent not found.")
        except Exception as e:
            await query.message.reply_text(f"❌ Error setting up delete: {e}")
            
    elif data.startswith("torrent_delconf:"):
        h = data.split(":", 1)[1]
        try:
            qbt = QBitClientWrapper()
            qbt.delete_torrent(h, delete_files=False)
            await query.edit_message_text("🗑 Deleted torrent. Downloaded files were kept.")
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to delete: {e}")
            
    elif data.startswith("torrent_delfiles:"):
        h = data.split(":", 1)[1]
        try:
            qbt = QBitClientWrapper()
            qbt.delete_torrent(h, delete_files=True)
            await query.edit_message_text("🔥 Deleted torrent and all associated files.")
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to delete files: {e}")
            
    elif data == "torrent_cancel":
        await refresh_progress_message(query.message)
        
    elif data.startswith("dl_hit:"):
        cache_id = int(data.split(":", 1)[1])
        cache_item = database.get_cached_search_result(cache_id)
        if cache_item:
            file_url = cache_item['file_url']
            file_name = cache_item['file_name']
            try:
                qbt = QBitClientWrapper()
                qbt.add_torrent(file_url)
                await query.message.reply_text(f"📥 *Started download for*:\n{file_name}", parse_mode="Markdown")
            except Exception as e:
                await query.message.reply_text(f"❌ Failed to start download: {e}")
        else:
            await query.message.reply_text("❌ Search link expired. Please perform the search again.")
            
    elif data.startswith("fav_add:"):
        cache_id = int(data.split(":", 1)[1])
        cache_item = database.get_cached_search_result(cache_id)
        if cache_item and cache_item['file_url'] == "favorite_query":
            term = cache_item['file_name']
            # We save the chat_id so we know where to send alerts
            success = database.add_favorite(term, query.message.chat_id)
            if success:
                await query.message.reply_text(f"⭐ Saved '{term}' to favorites. You will be alerted of new matches.")
            else:
                await query.message.reply_text(f"ℹ️ '{term}' is already in your favorites.")
        else:
            await query.message.reply_text("❌ Term cache expired. Please search again to save.")
            
    elif data.startswith("fav_del:"):
        fav_id = int(data.split(":", 1)[1])
        if database.remove_favorite(fav_id):
            await refresh_favorites_message(query.message)
        else:
            await query.message.reply_text("❌ Failed to remove favorite: item not found.")

# --- Main Entry Point ---

def main():
    # 1. Validate environment configuration
    validation_errors = Config.validate()
    if validation_errors:
        for err in validation_errors:
            logger.error(err)
        print("❌ Environment configuration errors detected. Exiting.")
        return
        
    # 2. Initialize Database
    try:
        database.init_db()
        logger.info("SQLite database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite: {e}")
        return
        
    # 3. Create Telegram bot application
    app = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
    
    # 4. Register command and query handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", start_handler))
    app.add_handler(CommandHandler("storage", storage_handler))
    app.add_handler(CommandHandler("progress", progress_handler))
    app.add_handler(CommandHandler("active", progress_handler))
    app.add_handler(CommandHandler("search", search_handler))
    app.add_handler(CommandHandler("favorites", favorites_handler))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # 5. Schedule periodic search check
    interval_seconds = Config.ALERT_INTERVAL_MINUTES * 60
    # Run once at startup (after 10s delay), then run repeatedly
    app.job_queue.run_repeating(check_search_alerts, interval=interval_seconds, first=10)
    logger.info(f"Scheduled search alert monitor every {Config.ALERT_INTERVAL_MINUTES} minutes.")
    
    # 6. Start the bot polling
    logger.info("qBittorrent Telegram Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
