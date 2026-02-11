import os
import json
import time
import random
import requests
import re
import atexit
from datetime import datetime, timedelta
from telebot import TeleBot, types
from telebot.util import quick_markup
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
import threading
from collections import defaultdict
from flask import Flask, jsonify
import logging
from threading import Thread

# ================== CONFIGURATION ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.environ.get('PORT', 5000))

# Disable excessive logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('telebot').setLevel(logging.ERROR)  # Changed to ERROR only
logging.getLogger('requests').setLevel(logging.WARNING)

if not TOKEN:
    print("❌ ERROR: TELEGRAM_TOKEN not found in environment variables")
    exit(1)

bot = TeleBot(TOKEN)

# Validate bot token
try:
    bot_info = bot.get_me()
    BOT_USERNAME = bot_info.username
    BOT_NAME = "Miss Tristin 💅"
    print(f"✅ Bot authenticated: @{BOT_USERNAME}")
except Exception as e:
    print(f"❌ Invalid bot token: {e}")
    exit(1)

START_TIME = time.time()

# Channel list for verification
CHANNELS = [
    "heiscoded",
    "evilpriest01",
    "Dev_Collins_Python_Lab"
]

# File paths
USERS_FILE = "users.json"
VERIFIED_FILE = "verified.json"
CONVERSATIONS_FILE = "conversations.json"  # NEW: Conversation memory file

# Developer credits
DEV1_USERNAME = "@Just_Collins101"
DEV2_USERNAME = "@heis_tomi"

# ================== CONVERSATION MEMORY ==================
# NEW: Persistent conversation memory
conversation_history = {}
MAX_HISTORY_PER_USER = 5  # Remember last 5 exchanges

def load_conversations():
    """Load conversation history from file"""
    global conversation_history
    try:
        if os.path.exists(CONVERSATIONS_FILE):
            with open(CONVERSATIONS_FILE, 'r', encoding='utf-8') as f:
                conversation_history = json.load(f)
            print(f"💬 Loaded {len(conversation_history)} conversations")
    except Exception as e:
        print(f"⚠️ Could not load conversations: {e}")
        conversation_history = {}

def save_conversations():
    """Save conversation history to file"""
    try:
        with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversation_history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error saving conversations: {e}")
        return False

def add_to_history(user_id, user_message, bot_response):
    """Add an exchange to conversation history"""
    user_id_str = str(user_id)
    
    if user_id_str not in conversation_history:
        conversation_history[user_id_str] = []
    
    # Add the exchange
    conversation_history[user_id_str].append({
        "user": user_message[:100],  # Limit length
        "bot": bot_response[:100],
        "timestamp": time.time()
    })
    
    # Keep only last MAX_HISTORY_PER_USER exchanges
    if len(conversation_history[user_id_str]) > MAX_HISTORY_PER_USER:
        conversation_history[user_id_str] = conversation_history[user_id_str][-MAX_HISTORY_PER_USER:]
    
    # Save periodically
    if random.random() < 0.3:  # 30% chance to save
        save_conversations()

def get_conversation_context(user_id):
    """Get recent conversation history for context"""
    user_id_str = str(user_id)
    if user_id_str not in conversation_history:
        return ""
    
    history = conversation_history[user_id_str]
    if not history:
        return ""
    
    # Format as conversation
    context_parts = []
    for exchange in history[-3:]:  # Last 3 exchanges
        context_parts.append(f"User: {exchange['user']}")
        context_parts.append(f"Miss Tristin: {exchange['bot']}")
    
    return "\n".join(context_parts)

# ================== ANTI-SPAM CONFIG ==================
USER_COOLDOWN = 0.8
user_last_message = defaultdict(float)
active_conversations = defaultdict(lambda: {"active": False, "timestamp": 0})
CONVERSATION_TIMEOUT = 10
user_message_counts = defaultdict(list)
SPAM_WINDOW = 8
SPAM_THRESHOLD = 6
chat_last_response = defaultdict(float)
CHAT_COOLDOWN = 0.5

# Track processed message IDs to prevent double responses
processed_messages = set()
PROCESSED_MESSAGE_EXPIRY = 60

def can_send_response(user_id, chat_id, message_id):
    """Check if we can send a response without spamming"""
    now = time.time()
    
    if message_id in processed_messages:
        return False
    
    if chat_id > 0:  # Private chat - more lenient
        user_message_counts[user_id] = [t for t in user_message_counts[user_id] 
                                       if now - t < SPAM_WINDOW]
        if len(user_message_counts[user_id]) >= SPAM_THRESHOLD + 2:
            return False
    else:  # Group chat
        if now - user_last_message[user_id] < USER_COOLDOWN:
            return False
        
        user_message_counts[user_id] = [t for t in user_message_counts[user_id] 
                                       if now - t < SPAM_WINDOW]
        if len(user_message_counts[user_id]) >= SPAM_THRESHOLD:
            return False
        
        if now - chat_last_response[chat_id] < CHAT_COOLDOWN:
            return False
    
    return True

def mark_response_sent(user_id, chat_id, message_id):
    """Mark that we've sent a response"""
    now = time.time()
    user_last_message[user_id] = now
    chat_last_response[chat_id] = now
    
    processed_messages.add(message_id)
    threading.Timer(PROCESSED_MESSAGE_EXPIRY, lambda: remove_processed_message(message_id)).start()
    
    conv_key = f"{user_id}:{chat_id}"
    active_conversations[conv_key] = {"active": True, "timestamp": now}
    threading.Timer(CONVERSATION_TIMEOUT, lambda: clear_conversation(user_id, chat_id)).start()

def remove_processed_message(message_id):
    """Remove message ID from processed set"""
    if message_id in processed_messages:
        processed_messages.remove(message_id)

def clear_conversation(user_id, chat_id):
    """Clear conversation marker"""
    conv_key = f"{user_id}:{chat_id}"
    active_conversations[conv_key]["active"] = False

# ================== COMMON ACRONYMS ==================
COMMON_ACRONYMS = {
    'dyw': 'do your worst',
    'wyd': 'what you doing',
    'hru': 'how are you',
    'wdym': 'what do you mean',
    'idk': 'i don\'t know',
    'tbh': 'to be honest',
    'fr': 'for real',
    'rn': 'right now',
    'lol': 'laugh out loud',
    'omg': 'oh my god',
    'brb': 'be right back',
    'gtg': 'got to go',
    'irl': 'in real life',
    'nvm': 'never mind',
    'jk': 'just kidding',
    'smh': 'shaking my head',
    'fyi': 'for your information',
    'imo': 'in my opinion',
    'imho': 'in my humble opinion',
    'tbf': 'to be fair',
    'afaik': 'as far as i know',
    'ikr': 'i know right',
    'nm': 'not much',
    'np': 'no problem',
    'ty': 'thank you',
    'yw': 'you\'re welcome',
    'gg': 'good game',
    'gl': 'good luck',
    'hf': 'have fun',
    'wb': 'welcome back',
    'asap': 'as soon as possible',
    'tf': 'the fuck',
    'tf?': 'the fuck',
    'wth': 'what the hell',
    'tfw': 'that feeling when'
}

def expand_acronyms(text):
    """Expand common acronyms in text"""
    words = text.split()
    expanded_words = []
    
    for word in words:
        clean_word = ''.join(c for c in word.lower() if c.isalnum())
        if clean_word in COMMON_ACRONYMS:
            expanded_words.append(COMMON_ACRONYMS[clean_word])
        else:
            expanded_words.append(word)
    
    return ' '.join(expanded_words)

# ================== RATE LIMITING ==================
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30
REQUEST_TIMEOUT = 12

user_requests = defaultdict(list)

def is_rate_limited(user_id=None):
    """Check if we're rate limited"""
    if user_id:
        now = time.time()
        user_requests[user_id] = [t for t in user_requests[user_id] 
                                  if now - t < RATE_LIMIT_WINDOW]
        if len(user_requests[user_id]) >= RATE_LIMIT_MAX:
            return True
    return False

def record_request(user_id=None):
    """Record a request for rate limiting"""
    now = time.time()
    if user_id:
        user_requests[user_id].append(now)
        user_message_counts[user_id].append(now)

# ================== RESPONSE CACHE ==================
response_cache = {}
CACHE_DURATION = 300

def get_cached_response(message):
    """Get cached response if available"""
    message_key = message.lower().strip()
    if message_key in response_cache:
        timestamp, response = response_cache[message_key]
        if time.time() - timestamp < CACHE_DURATION:
            return response
    return None

def cache_response(message, response):
    """Cache a response"""
    message_key = message.lower().strip()
    response_cache[message_key] = (time.time(), response)

# ================== COMMON GREETINGS ==================
COMMON_GREETINGS = {
    'hi': ["Hey! 👋", "Hi there! 😊", "Hello! 👀", "Hiiii 👋"],
    'hello': ["Hey! 😏", "Hello there! ✨", "Hi! 💁‍♀️", "Hiiii 👋"],
    'hey': ["Hey! 😌", "What's up? 👀", "Hey there! 💫", "Hey! 😊"],
    'how are you': ["I'm good 😊", "All good! 💖", "Sassy as ever 💅", "I'm good, you? 😊"],
    'how r u': ["I'm good 😊", "All good! 💖", "Sassy as ever 💅", "I'm good, you? 😊"],
    'whats up': ["Not much 😏", "Chilling! You? 👀", "Same old 😌", "What's good? 😊"],
    'sup': ["Not much 😏", "Chilling! You? 👀", "Same old 😌", "What's good? 😊"],
    'thanks': ["Welcome! 😊", "No problem! 💖", "Anytime! ✨"],
    'thank you': ["Welcome! 😊", "No problem! 💖", "Anytime! ✨"],
    'ty': ["Welcome! 😊", "No problem! 💖", "Anytime! ✨"],
    'yooo': ["Hiiii 👋", "Heyy! 😊", "Yo! 👀"],
    'yo': ["Hey! 😏", "Yo! 👀", "What's up? 😊"],
    'tf': ["What? 😏", "Something wrong? 👀", "You good? 🤔"],
    'lol': ["😂", "😭 fr?", "LOL", "😂😂"],
    'omg': ["I know right?! 😱", "OMG 😳", "No way! 😮"],
    'fr': ["Fr fr? 👀", "For real? 😏", "Deadass? 🤔"],
    'rangers': ["Duh, I'm not a Ranger. I'm more like a coffee-guzzling, Netflix-binging college girl. 🤪"],
    'assemble': ["Power Rangers? More like Power Nappers 😴", "Assembling my thoughts... give me a sec 💭"]
}

def get_common_response(message):
    """Check if message matches common greetings"""
    msg_lower = message.lower().strip()
    
    # Direct match
    if msg_lower in COMMON_GREETINGS:
        return random.choice(COMMON_GREETINGS[msg_lower])
    
    # Check words
    words = msg_lower.split()
    for word in words:
        if word in COMMON_GREETINGS:
            return random.choice(COMMON_GREETINGS[word])
    
    # Check for keywords
    if 'ranger' in msg_lower or 'assemble' in msg_lower:
        return random.choice(COMMON_GREETINGS.get('rangers', ["What's good? 🤔"]))
    
    return None

# ================== DATA MANAGEMENT ==================
def load_json(file_path, default_data=None):
    """Load JSON data from file"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading {file_path}: {e}")
    return default_data if default_data is not None else {}

def save_json(file_path, data):
    """Save data to JSON file"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error saving {file_path}: {e}")
        return False

# Load all data
users_data = load_json(USERS_FILE, {})
verified_users = load_json(VERIFIED_FILE, [])
load_conversations()  # Load conversation memory

def save_all_data():
    """Save all data to files"""
    save_json(USERS_FILE, users_data)
    save_json(VERIFIED_FILE, verified_users)
    save_conversations()
    print("💾 All data saved")

atexit.register(save_all_data)

def ensure_user_exists(user_id):
    """Ensure user exists in database"""
    user_id_str = str(user_id)
    
    if user_id_str not in users_data:
        users_data[user_id_str] = {
            "messages": 0,
            "first_seen": datetime.now().isoformat(),
            "last_interaction": datetime.now().isoformat()
        }
    
    users_data[user_id_str]["messages"] += 1
    users_data[user_id_str]["last_interaction"] = datetime.now().isoformat()
    
    return users_data[user_id_str]

def is_user_verified(user_id):
    """Check if user is verified"""
    return str(user_id) in verified_users

def verify_user_id(user_id):
    """Add user to verified list"""
    user_id_str = str(user_id)
    if user_id_str not in verified_users:
        verified_users.append(user_id_str)
        save_json(VERIFIED_FILE, verified_users)
        return True
    return False

# ================== HELPER FUNCTIONS ==================
def safe_edit_message(chat_id, message_id, text, reply_markup=None):
    """Safely edit a message"""
    try:
        bot.edit_message_text(
            text,
            chat_id,
            message_id,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return True
    except Exception:
        return False

# ================== KEYBOARD GENERATORS ==================
def get_main_menu_keyboard():
    """Generate the main menu keyboard"""
    return quick_markup({
        '🔥 Help': {'callback_data': 'help'},
        '😎 About': {'callback_data': 'about'},
        '✂️ RPS': {'callback_data': 'rps'},
        '📊 Stats': {'callback_data': 'stats'},
        '⏱ Uptime': {'callback_data': 'uptime'}
    }, row_width=2)

def get_back_button():
    """Generate back to menu button"""
    return quick_markup({
        '👈 Back': {'callback_data': 'back_to_menu'}
    })

def get_verification_keyboard():
    """Generate verification keyboard"""
    markup = types.InlineKeyboardMarkup()
    
    for channel in CHANNELS:
        markup.add(
            types.InlineKeyboardButton(
                f"🔗 Join @{channel}",
                url=f"https://t.me/{channel}"
            )
        )
    
    markup.add(
        types.InlineKeyboardButton(
            "✅ I Joined All!",
            callback_data="verify"
        )
    )
    
    return markup

# ================== VERIFICATION SYSTEM ==================
def check_channel_membership(user_id, channel_username):
    """Check if user is a member of a channel"""
    try:
        clean_username = channel_username.replace('@', '')
        chat_member = bot.get_chat_member(clean_username, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

@bot.callback_query_handler(func=lambda call: call.data == 'verify')
def handle_verification(call):
    """Handle verification callback"""
    user_id = call.from_user.id
    
    if is_user_verified(user_id):
        bot.answer_callback_query(call.id, "Already verified! 😒")
        safe_edit_message(
            call.message.chat.id,
            call.message.message_id,
            "<b>You're already verified!</b>\n\nWhat now? 👇",
            get_main_menu_keyboard()
        )
        return
    
    missing_channels = []
    for channel in CHANNELS:
        if not check_channel_membership(user_id, channel):
            missing_channels.append(f"@{channel}")
    
    if missing_channels:
        bot.answer_callback_query(call.id, f"Missing {len(missing_channels)} channel(s)!")
        channel_list = "\n".join([f"• {ch}" for ch in missing_channels])
        safe_edit_message(
            call.message.chat.id,
            call.message.message_id,
            f"❌ <b>You haven't joined:</b>\n{channel_list}\n\nJoin ALL channels first!",
            get_verification_keyboard()
        )
    else:
        verify_user_id(user_id)
        bot.answer_callback_query(call.id, "✅ Verified!")
        safe_edit_message(
            call.message.chat.id,
            call.message.message_id,
            "✅ <b>Verification Successful!</b>\n\nWhat now? 👇",
            get_main_menu_keyboard()
        )

# ================== COMMAND HANDLERS ==================
@bot.message_handler(commands=['start', 'help', 'menu'])
def handle_start(message):
    """Handle /start command"""
    user_id = message.from_user.id
    ensure_user_exists(user_id)
    
    if not is_user_verified(user_id):
        channel_list = "\n".join([f"• @{ch}" for ch in CHANNELS])
        welcome_msg = (
            f"👋 <b>Hey {message.from_user.first_name}!</b>\n\n"
            f"Join ALL my channels then click verify:\n\n"
            f"{channel_list}"
        )
        bot.send_message(
            message.chat.id,
            welcome_msg,
            parse_mode="HTML",
            reply_markup=get_verification_keyboard()
        )
    else:
        welcome_msg = (
            f"Oh, it's you... 👀\n\n"
            f"<b>Miss Tristin here. 20. American.</b>\n"
            f"What do you want? 👇"
        )
        bot.send_message(
            message.chat.id,
            welcome_msg,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )

@bot.message_handler(commands=['clear'])
def handle_clear(message):
    """Clear conversation history"""
    if not is_user_verified(message.from_user.id):
        return
    
    user_id = str(message.from_user.id)
    if user_id in conversation_history:
        conversation_history[user_id] = []
        save_conversations()
        bot.reply_to(message, "🧹 Memory cleared!")
    else:
        bot.reply_to(message, "Nothing to clear 😏")

@bot.message_handler(commands=['stats'])
def handle_stats_command(message):
    """Show user stats"""
    if not is_user_verified(message.from_user.id):
        return
    
    user_id = str(message.from_user.id)
    user_data = users_data.get(user_id, {})
    msg_count = user_data.get('messages', 0)
    
    stats_text = (
        f"<b>📊 YOUR STATS</b>\n\n"
        f"Messages: {msg_count}\n"
        f"First seen: {user_data.get('first_seen', 'N/A')[:10]}\n"
        f"Conversations saved: {len(conversation_history.get(user_id, []))}"
    )
    bot.reply_to(message, stats_text, parse_mode="HTML")

# ================== CALLBACK QUERY HANDLERS ==================
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_menu')
def handle_back_to_menu(call):
    """Handle back to menu callback"""
    bot.answer_callback_query(call.id, "Back to menu")
    safe_edit_message(
        call.message.chat.id,
        call.message.message_id,
        "<b>Back so soon?</b>\n\nWhat now? 👇",
        get_main_menu_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'help')
def handle_help(call):
    """Show help information"""
    help_text = (
        "<b>🔥 HELP</b>\n\n"
        "<b>Commands:</b>\n"
        "• define [word] - Get definition\n"
        "• translate en fr [text] - Translate\n"
        "• rock/paper/scissors - Play RPS\n"
        "• /clear - Clear my memory of you\n"
        "• /stats - Your stats\n\n"
        "<b>Chat:</b>\n"
        "• @mention me\n"
        "• Reply to me\n"
        "• Say 'Tristin'\n"
        "• Private message me\n\n"
        "<i>I remember our last 5 messages 💭</i>"
    )
    safe_edit_message(
        call.message.chat.id,
        call.message.message_id,
        help_text,
        get_back_button()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'about')
def handle_about(call):
    """Show about information"""
    about_text = (
        "<b>😎 ABOUT</b>\n\n"
        f"Creators: {DEV1_USERNAME} & {DEV2_USERNAME}\n\n"
        "<i>Built to entertain, coded to sass 💅</i>\n\n"
        f"🤖 @{BOT_USERNAME}"
    )
    safe_edit_message(
        call.message.chat.id,
        call.message.message_id,
        about_text,
        get_back_button()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'rps')
def handle_rps_instructions(call):
    """Show RPS game instructions"""
    text = (
        "<b>✂️ ROCK PAPER SCISSORS</b>\n\n"
        "Just send: rock, paper, or scissors\n\n"
        "<i>I'll go easy... maybe 😏</i>"
    )
    safe_edit_message(
        call.message.chat.id,
        call.message.message_id,
        text,
        get_back_button()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'stats')
def handle_stats_callback(call):
    """Show bot statistics"""
    total_users = len(users_data)
    total_messages = sum(user.get('messages', 0) for user in users_data.values())
    verified_count = len(verified_users)
    conversations_count = len(conversation_history)
    
    stats_text = (
        f"<b>📊 BOT STATS</b>\n\n"
        f"Users: {total_users}\n"
        f"Messages: {total_messages}\n"
        f"Verified: {verified_count}\n"
        f"Conversations: {conversations_count}"
    )
    
    safe_edit_message(
        call.message.chat.id,
        call.message.message_id,
        stats_text,
        get_back_button()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'uptime')
def handle_uptime(call):
    """Show bot uptime"""
    uptime_seconds = int(time.time() - START_TIME)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    
    if days > 0:
        uptime_str = f"{days}d {hours}h"
    else:
        uptime_str = f"{hours}h {minutes}m"
    
    uptime_text = f"<b>⏱ UPTIME</b>\n\n{uptime_str}"
    
    safe_edit_message(
        call.message.chat.id,
        call.message.message_id,
        uptime_text,
        get_back_button()
    )

# ================== GAME HANDLERS ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['rock', 'paper', 'scissors'])
def handle_rps_game(message):
    """Handle Rock Paper Scissors game"""
    if not is_user_verified(message.from_user.id):
        return
    
    if message.message_id in processed_messages:
        return
    
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
    
    user_choice = message.text.lower()
    bot_choice = random.choice(['rock', 'paper', 'scissors'])
    
    if user_choice == bot_choice:
        result = "Draw! 😒"
        reaction = "🤝"
    elif (user_choice == 'rock' and bot_choice == 'scissors') or \
         (user_choice == 'paper' and bot_choice == 'rock') or \
         (user_choice == 'scissors' and bot_choice == 'paper'):
        result = "You win 😏"
        reaction = "😤"
    else:
        result = "I win! 😌"
        reaction = "🎉"
    
    response = f"<b>✂️ RPS</b>\n\nYou: {user_choice}\nMe: {bot_choice}\n\n{result} {reaction}"
    bot.reply_to(message, response, parse_mode="HTML")
    
    # Save to conversation memory
    add_to_history(message.from_user.id, f"played {user_choice}", response)

# ================== WORD DEFINITION HANDLER ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith('define '))
def handle_define_word(message):
    """Define words using dictionary API"""
    if not is_user_verified(message.from_user.id):
        return
    
    if message.message_id in processed_messages:
        return
    
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    try:
        word = message.text.split(' ', 1)[1].strip()
        
        if not word:
            bot.reply_to(message, "Define what? 🙄")
            return
        
        mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
        
        response = requests.get(
            f'https://api.dictionaryapi.dev/api/v2/entries/en/{word}',
            headers={'User-Agent': 'MissTristinBot/1.0'},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            definition = data[0]['meanings'][0]['definitions'][0]['definition']
            reply = f"<b>📖 {word.upper()}</b>\n\n{definition}"
            bot.reply_to(message, reply, parse_mode="HTML")
            
            # Save to conversation memory
            add_to_history(message.from_user.id, f"define {word}", reply)
        else:
            reply = f"'{word}'? Never heard of it. 🙄"
            bot.reply_to(message, reply)
            add_to_history(message.from_user.id, f"define {word}", reply)
            
    except Exception:
        bot.reply_to(message, "That word doesn't exist... or reality. 😏")

# ================== TRANSLATION HANDLER ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith('translate '))
def handle_translation(message):
    """Translate text between languages"""
    if not is_user_verified(message.from_user.id):
        return
    
    if message.message_id in processed_messages:
        return
    
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    try:
        parts = message.text.split(' ', 3)
        
        if len(parts) < 4:
            bot.reply_to(message, "Use: translate en fr Hello", parse_mode="HTML")
            return
        
        _, from_lang, to_lang, text = parts
        from_lang = from_lang[:2].lower()
        to_lang = to_lang[:2].lower()
        
        if not text.strip():
            return
        
        mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
        
        translator = GoogleTranslator(source=from_lang, target=to_lang)
        translated_text = translator.translate(text)
        
        reply = f"<b>🌍 TRANSLATION</b>\n\n{translated_text}"
        bot.reply_to(message, reply, parse_mode="HTML")
        
        # Save to conversation memory
        add_to_history(message.from_user.id, f"translate {text[:30]}...", reply)
        
    except Exception:
        bot.reply_to(message, "Translation failed 😒")

# ================== AI CHAT HANDLER ==================
def process_ai_request(user_message, user_id, first_name, chat_id, message_obj, is_mention=False):
    """Process AI request with rate limiting and conversation memory"""
    
    if not user_message or len(user_message.strip()) == 0:
        if is_mention:
            reply = f"Yeah? 👀"
            bot.reply_to(message_obj, reply)
            add_to_history(user_id, "[empty mention]", reply)
        return
    
    user_message_expanded = expand_acronyms(user_message)

    # Check cache
    cached = get_cached_response(user_message_expanded)
    if cached:
        bot.reply_to(message_obj, cached)
        add_to_history(user_id, user_message, cached)
        return

    # Check common responses
    common_response = get_common_response(user_message_expanded)
    if common_response:
        bot.reply_to(message_obj, common_response)
        cache_response(user_message_expanded, common_response)
        add_to_history(user_id, user_message, common_response)
        return

    # Check rate limits
    if is_rate_limited(user_id):
        responses = [
            f"Slow down, {first_name}! 😏",
            f"Easy there, {first_name}! 😅",
            f"Chill, {first_name}! ⏳"
        ]
        reply = random.choice(responses)
        bot.reply_to(message_obj, reply)
        add_to_history(user_id, user_message, reply)
        return

    record_request(user_id)
    bot.send_chat_action(chat_id, 'typing')

    # Get conversation context
    context = get_conversation_context(user_id)

    # Use AI if key exists
    if GROQ_KEY and GROQ_KEY != "your_groq_api_key_here":
        system_prompt = (
            "You are Miss Tristin, a 20-year-old American girl. "
            "Keep responses under 150 characters. Be brief and sassy. "
            "Never mention being AI. Use emojis sparingly. "
            "Be casual and conversational like a real person. "
            "Remember the conversation context and be consistent."
        )

        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add context if exists
        if context:
            messages.append({"role": "system", "content": f"Recent conversation:\n{context}"})
        
        # Add current message
        messages.append({"role": "user", "content": user_message_expanded[:200]})

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 100
        }

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                reply = data["choices"][0]["message"]["content"].strip()
                cache_response(user_message_expanded, reply)
                bot.reply_to(message_obj, reply)
                add_to_history(user_id, user_message, reply)
                return

        except Exception as e:
            print(f"⚠️ Groq API exception: {e}")

    # Fallback responses with context awareness
    if is_mention:
        fallbacks = [
            f"Yeah? 👀",
            f"What's up? 😏",
            f"I'm listening... 💁‍♀️",
            f"You called? 😌",
            f"Hmm? 💅",
            f"idk, what's good? 🤔",
            f"Interesting... 🤔"
        ]
    else:
        fallbacks = [
            f"Say that again? 😏",
            f"Interesting... 😌",
            f"Go on... 👀",
            f"Yeah? 💁‍♀️",
            f"Uh huh... 💅",
            f"idk, what's good? 🤔"
        ]
    
    reply = random.choice(fallbacks)
    bot.reply_to(message_obj, reply)
    add_to_history(user_id, user_message, reply)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_chat(message):
    """Handle regular chat messages"""
    
    if message.text.startswith('/'):
        return
    
    if not is_user_verified(message.from_user.id):
        return
    
    if message.message_id in processed_messages:
        return

    ensure_user_exists(message.from_user.id)

    # TRIGGER DETECTION
    should_respond = False
    is_mention = False
    clean_message = message.text
    
    bot_username_mention = f"@{BOT_USERNAME}"

    # Case 1: Private chat
    if message.chat.type == 'private':
        should_respond = True
        is_mention = True

    # Case 2: Direct mention
    elif bot_username_mention.lower() in message.text.lower():
        should_respond = True
        is_mention = True
        pattern = re.compile(re.escape(bot_username_mention), re.IGNORECASE)
        clean_message = pattern.sub('', message.text).strip()

    # Case 3: Reply to bot
    elif message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot_info.id:
            should_respond = True
            is_mention = True

    # Case 4: Name triggers
    elif any(trigger in message.text.lower() for trigger in ['tristin', 'derieri', 'miss tristin']):
        should_respond = True
        is_mention = True
        clean_message = message.text
        for trigger in ['tristin', 'derieri', 'miss tristin']:
            pattern = re.compile(re.escape(trigger), re.IGNORECASE)
            clean_message = pattern.sub('', clean_message).strip()

    if not should_respond:
        return

    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return

    mark_response_sent(message.from_user.id, message.chat.id, message.message_id)

    process_ai_request(
        clean_message,
        message.from_user.id,
        message.from_user.first_name,
        message.chat.id,
        message,
        is_mention
    )

# ================== UNSUPPORTED CONTENT ==================
@bot.message_handler(func=lambda message: True, content_types=['audio', 'document', 'photo', 'sticker', 'video', 'voice', 'location', 'contact'])
def handle_unsupported(message):
    """Handle unsupported content types"""
    if not is_user_verified(message.from_user.id):
        return
    
    if message.message_id in processed_messages:
        return
    
    if can_send_response(message.from_user.id, message.chat.id, message.message_id):
        mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
        roasts = [
            f"Text only, {message.from_user.first_name}. 😏",
            f"Use your words... I know you have them. 😌",
            f"Nice try. Now type something. 😑",
            f"I don't do files. 💅",
            f"Send text or don't send at all. 🙄"
        ]
        reply = random.choice(roasts)
        bot.reply_to(message, reply)
        add_to_history(message.from_user.id, "[non-text message]", reply)

# ================== FLASK SERVER ==================
app = Flask(__name__)

@app.route('/')
def home():
    """Dummy endpoint for uptime monitoring"""
    uptime_seconds = int(time.time() - START_TIME)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60

    return jsonify({
        'status': 'alive',
        'bot': 'Miss Tristin 💅',
        'username': f"@{BOT_USERNAME}",
        'uptime': f"{days}d {hours}h {minutes}m",
        'users': len(users_data),
        'verified': len(verified_users),
        'conversations': len(conversation_history)
    })

@app.route('/ping')
def ping():
    """Ping endpoint for monitoring services"""
    return jsonify({'pong': True, 'timestamp': time.time()})

def run_flask():
    """Run Flask server in a separate thread"""
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"⚠️ Flask server error: {e}")

# ================== START BOT ==================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🔥 MISS TRISTIN IS AWAKE 🔥")
    print(f"🤖 @{BOT_USERNAME}")
    print("="*50)
    print(f"📊 Users: {len(users_data)}")
    print(f"✅ Verified: {len(verified_users)}")
    print(f"💬 Conversations: {len(conversation_history)}")
    print(f"📁 Data files: {USERS_FILE}, {VERIFIED_FILE}, {CONVERSATIONS_FILE}")

    if not GROQ_KEY or GROQ_KEY == "your_groq_api_key_here":
        print("⚠️ AI chat: Using fallback responses only")
    else:
        print(f"🤖 Groq: Connected")

    print("\n🚀 TRIGGERS ACTIVE:")
    print(f"   • @{BOT_USERNAME} [mention]")
    print(f"   • Reply to bot")
    print(f"   • 'Tristin', 'Derieri', 'Miss Tristin'")
    print(f"   • Private chat")
    print("="*50 + "\n")

    # Save data on startup
    save_all_data()

    # Start Flask server
    try:
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"🌐 Web server running on port {PORT}")
    except Exception as e:
        print(f"⚠️ Could not start web server: {e}")
    
    print("🚀 Bot is polling...\n")
    
    # FIXED: Simple polling without the infinite error loop
    try:
        bot.polling(none_stop=True, interval=0.5, timeout=60)
    except Exception as e:
        print(f"⚠️ Polling error: {e}")
        time.sleep(5)
        try:
            bot.polling(none_stop=True, interval=0.5, timeout=60)
        except:
            print("❌ Fatal polling error. Restart manually.")
