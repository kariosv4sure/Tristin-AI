import os
import json
import time
import random
import requests
import re
import atexit
from datetime import datetime
from telebot import TeleBot, types
from telebot.util import quick_markup
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
import threading
from collections import defaultdict
from flask import Flask, jsonify
import logging

# ================== CONFIGURATION ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.environ.get('PORT', 10000))

# Disable excessive logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('telebot').setLevel(logging.ERROR)

if not TOKEN:
    print("❌ ERROR: TELEGRAM_TOKEN not found")
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

# ================== RENDER VS LOCAL ==================
IS_RENDER = 'RENDER' in os.environ

if IS_RENDER:
    USERS_FILE = "/tmp/users.json"
    VERIFIED_FILE = "/tmp/verified.json"
    CONVERSATIONS_FILE = "/tmp/conversations.json"
else:
    USERS_FILE = "users.json"
    VERIFIED_FILE = "verified.json"
    CONVERSATIONS_FILE = "conversations.json"
    os.makedirs("data", exist_ok=True)

# Channel list for verification
CHANNELS = ["heiscoded", "evilpriest01", "Dev_Collins_Python_Lab"]

# Developer credits
DEV1_USERNAME = "@Just_Collins101"
DEV2_USERNAME = "@heis_tomi"

# ================== CONVERSATION MEMORY ==================
conversation_history = {}
MAX_HISTORY_PER_USER = 5

def load_conversations():
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
    try:
        with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversation_history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error saving conversations: {e}")
        return False

def add_to_history(user_id, user_message, bot_response):
    user_id_str = str(user_id)
    if user_id_str not in conversation_history:
        conversation_history[user_id_str] = []
    
    conversation_history[user_id_str].append({
        "user": user_message[:100],
        "bot": bot_response[:100],
        "timestamp": time.time()
    })
    
    if len(conversation_history[user_id_str]) > MAX_HISTORY_PER_USER:
        conversation_history[user_id_str] = conversation_history[user_id_str][-MAX_HISTORY_PER_USER:]
    
    if random.random() < 0.3:
        save_conversations()

def get_conversation_context(user_id):
    user_id_str = str(user_id)
    if user_id_str not in conversation_history:
        return ""
    
    history = conversation_history[user_id_str]
    if not history:
        return ""
    
    context_parts = []
    for exchange in history[-3:]:
        context_parts.append(f"User: {exchange['user']}")
        context_parts.append(f"Miss Tristin: {exchange['bot']}")
    
    return "\n".join(context_parts)

# ================== DATA MANAGEMENT ==================
def load_json(file_path, default_data=None):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading {file_path}: {e}")
    return default_data if default_data is not None else {}

def save_json(file_path, data):
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
load_conversations()

def save_all_data():
    save_json(USERS_FILE, users_data)
    save_json(VERIFIED_FILE, verified_users)
    save_conversations()
    print("💾 All data saved")

atexit.register(save_all_data)

def ensure_user_exists(user_id):
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
    return str(user_id) in verified_users

def verify_user_id(user_id):
    user_id_str = str(user_id)
    if user_id_str not in verified_users:
        verified_users.append(user_id_str)
        save_json(VERIFIED_FILE, verified_users)
        return True
    return False

# ================== ANTI-SPAM ==================
USER_COOLDOWN = 0.8
user_last_message = defaultdict(float)
active_conversations = defaultdict(lambda: {"active": False, "timestamp": 0})
CONVERSATION_TIMEOUT = 10
user_message_counts = defaultdict(list)
SPAM_WINDOW = 8
SPAM_THRESHOLD = 6
chat_last_response = defaultdict(float)
CHAT_COOLDOWN = 0.5
processed_messages = set()
PROCESSED_MESSAGE_EXPIRY = 60

def can_send_response(user_id, chat_id, message_id):
    now = time.time()
    if message_id in processed_messages:
        return False
    
    if chat_id > 0:  # Private chat
        user_message_counts[user_id] = [t for t in user_message_counts[user_id] if now - t < SPAM_WINDOW]
        if len(user_message_counts[user_id]) >= SPAM_THRESHOLD + 2:
            return False
    else:  # Group chat
        if now - user_last_message[user_id] < USER_COOLDOWN:
            return False
        user_message_counts[user_id] = [t for t in user_message_counts[user_id] if now - t < SPAM_WINDOW]
        if len(user_message_counts[user_id]) >= SPAM_THRESHOLD:
            return False
        if now - chat_last_response[chat_id] < CHAT_COOLDOWN:
            return False
    return True

def mark_response_sent(user_id, chat_id, message_id):
    now = time.time()
    user_last_message[user_id] = now
    chat_last_response[chat_id] = now
    processed_messages.add(message_id)
    threading.Timer(PROCESSED_MESSAGE_EXPIRY, lambda: processed_messages.discard(message_id)).start()
    
    conv_key = f"{user_id}:{chat_id}"
    active_conversations[conv_key] = {"active": True, "timestamp": now}
    threading.Timer(CONVERSATION_TIMEOUT, lambda: active_conversations.update({conv_key: {"active": False, "timestamp": now}})).start()

# ================== COMMON ACRONYMS ==================
COMMON_ACRONYMS = {
    'dyw': 'do your worst', 'wyd': 'what you doing', 'hru': 'how are you',
    'wdym': 'what do you mean', 'idk': 'i don\'t know', 'tbh': 'to be honest',
    'fr': 'for real', 'rn': 'right now', 'lol': 'laugh out loud',
    'omg': 'oh my god', 'brb': 'be right back', 'gtg': 'got to go',
    'irl': 'in real life', 'nvm': 'never mind', 'jk': 'just kidding',
    'smh': 'shaking my head', 'fyi': 'for your information',
    'imo': 'in my opinion', 'imho': 'in my humble opinion',
    'tbf': 'to be fair', 'afaik': 'as far as i know', 'ikr': 'i know right',
    'nm': 'not much', 'np': 'no problem', 'ty': 'thank you',
    'yw': 'you\'re welcome', 'gg': 'good game', 'gl': 'good luck',
    'hf': 'have fun', 'wb': 'welcome back', 'asap': 'as soon as possible',
    'tf': 'the fuck', 'wth': 'what the hell', 'tfw': 'that feeling when'
}

def expand_acronyms(text):
    words = text.split()
    expanded = []
    for word in words:
        clean = ''.join(c for c in word.lower() if c.isalnum())
        expanded.append(COMMON_ACRONYMS.get(clean, word))
    return ' '.join(expanded)

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
    msg = message.lower().strip()
    if msg in COMMON_GREETINGS:
        return random.choice(COMMON_GREETINGS[msg])
    words = msg.split()
    for word in words:
        if word in COMMON_GREETINGS:
            return random.choice(COMMON_GREETINGS[word])
    if 'ranger' in msg or 'assemble' in msg:
        return random.choice(COMMON_GREETINGS.get('rangers', ["What's good? 🤔"]))
    return None

# ================== KEYBOARDS ==================
def get_verification_keyboard():
    markup = types.InlineKeyboardMarkup()
    for channel in CHANNELS:
        markup.add(types.InlineKeyboardButton(f"🔗 Join @{channel}", url=f"https://t.me/{channel}"))
    markup.add(types.InlineKeyboardButton("✅ I Joined All!", callback_data="verify"))
    return markup

def get_main_menu_keyboard():
    return quick_markup({
        '🔥 Help': {'callback_data': 'help'},
        '😎 About': {'callback_data': 'about'},
        '✂️ RPS': {'callback_data': 'rps'},
        '📊 Stats': {'callback_data': 'stats'},
        '⏱ Uptime': {'callback_data': 'uptime'}
    }, row_width=2)

def get_back_button():
    return quick_markup({'👈 Back': {'callback_data': 'back_to_menu'}})

# ================== HELPER FUNCTIONS ==================
def safe_edit_message(chat_id, msg_id, text, markup=None):
    try:
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)
        return True
    except:
        return False

def check_channel_membership(user_id, channel):
    try:
        clean = channel.replace('@', '')
        member = bot.get_chat_member(clean, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# ================== VERIFICATION ==================
@bot.callback_query_handler(func=lambda call: call.data == 'verify')
def handle_verification(call):
    uid = str(call.from_user.id)
    if is_user_verified(uid):
        bot.answer_callback_query(call.id, "Already verified! 😒")
        safe_edit_message(call.message.chat.id, call.message.message_id, 
                         "<b>You're already verified!</b>\n\nWhat now? 👇", get_main_menu_keyboard())
        return
    
    missing = [f"@{ch}" for ch in CHANNELS if not check_channel_membership(uid, ch)]
    if missing:
        bot.answer_callback_query(call.id, f"Missing {len(missing)} channel(s)!")
        channel_list = "\n".join([f"• {ch}" for ch in missing])
        safe_edit_message(call.message.chat.id, call.message.message_id,
                         f"❌ <b>You haven't joined:</b>\n{channel_list}\n\nJoin ALL channels first!",
                         get_verification_keyboard())
    else:
        verify_user_id(uid)
        bot.answer_callback_query(call.id, "✅ Verified!")
        safe_edit_message(call.message.chat.id, call.message.message_id,
                         "✅ <b>Verification Successful!</b>\n\nWhat now? 👇", get_main_menu_keyboard())

# ================== COMMAND HANDLERS ==================
@bot.message_handler(commands=['start', 'help', 'menu'])
def handle_start(message):
    uid = message.from_user.id
    ensure_user_exists(uid)
    
    if not is_user_verified(uid):
        channel_list = "\n".join([f"• @{ch}" for ch in CHANNELS])
        bot.send_message(message.chat.id,
                        f"👋 <b>Hey {message.from_user.first_name}!</b>\n\nJoin ALL my channels then click verify:\n\n{channel_list}",
                        parse_mode="HTML", reply_markup=get_verification_keyboard())
    else:
        bot.send_message(message.chat.id,
                        f"Oh, it's you... 👀\n\n<b>Miss Tristin here. 20. American.</b>\nWhat do you want? 👇",
                        parse_mode="HTML", reply_markup=get_main_menu_keyboard())

@bot.message_handler(commands=['clear'])
def handle_clear(message):
    if not is_user_verified(message.from_user.id):
        return
    uid = str(message.from_user.id)
    if uid in conversation_history:
        conversation_history[uid] = []
        save_conversations()
        bot.reply_to(message, "🧹 Memory cleared!")
    else:
        bot.reply_to(message, "Nothing to clear 😏")

# ================== CALLBACK HANDLERS ==================
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_menu')
def back_to_menu(call):
    bot.answer_callback_query(call.id, "Back to menu")
    safe_edit_message(call.message.chat.id, call.message.message_id,
                     "<b>Back so soon?</b>\n\nWhat now? 👇", get_main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == 'help')
def help_callback(call):
    help_text = ("<b>🔥 HELP</b>\n\n<b>Commands:</b>\n• define [word]\n• translate en fr [text]\n"
                "• rock/paper/scissors\n• /clear - Clear memory\n\n<b>Chat:</b>\n• @mention me\n"
                "• Reply to me\n• Say 'Tristin'\n• Private message\n\n<i>I remember our last 5 messages 💭</i>")
    safe_edit_message(call.message.chat.id, call.message.message_id, help_text, get_back_button())

@bot.callback_query_handler(func=lambda call: call.data == 'about')
def about_callback(call):
    about_text = f"<b>😎 ABOUT</b>\n\nCreators: {DEV1_USERNAME} & {DEV2_USERNAME}\n\n<i>Built to entertain, coded to sass 💅</i>"
    safe_edit_message(call.message.chat.id, call.message.message_id, about_text, get_back_button())

@bot.callback_query_handler(func=lambda call: call.data == 'rps')
def rps_callback(call):
    text = "<b>✂️ ROCK PAPER SCISSORS</b>\n\nJust send: rock, paper, or scissors\n\n<i>I'll go easy... maybe 😏</i>"
    safe_edit_message(call.message.chat.id, call.message.message_id, text, get_back_button())

@bot.callback_query_handler(func=lambda call: call.data == 'stats')
def stats_callback(call):
    stats_text = (f"<b>📊 STATS</b>\n\nUsers: {len(users_data)}\n"
                 f"Messages: {sum(u.get('messages',0) for u in users_data.values())}\n"
                 f"Verified: {len(verified_users)}\nConversations: {len(conversation_history)}")
    safe_edit_message(call.message.chat.id, call.message.message_id, stats_text, get_back_button())

@bot.callback_query_handler(func=lambda call: call.data == 'uptime')
def uptime_callback(call):
    seconds = int(time.time() - START_TIME)
    days, rem = divmod(seconds, 86400)
    hours, mins = divmod(rem, 3600)
    uptime = f"{days}d {hours}h" if days > 0 else f"{hours}h {mins}m"
    safe_edit_message(call.message.chat.id, call.message.message_id,
                     f"<b>⏱ UPTIME</b>\n\n{uptime}", get_back_button())

# ================== GAME HANDLER ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['rock', 'paper', 'scissors'])
def handle_rps(message):
    if not is_user_verified(message.from_user.id) or message.message_id in processed_messages:
        return
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
    
    # 🔥 TYPING EFFECT
    bot.send_chat_action(message.chat.id, 'typing')
    time.sleep(0.3)  # Small delay for effect
    
    user = message.text.lower()
    bot_choice = random.choice(['rock', 'paper', 'scissors'])
    
    if user == bot_choice:
        result, react = "Draw! 😒", "🤝"
    elif (user == 'rock' and bot_choice == 'scissors') or \
         (user == 'paper' and bot_choice == 'rock') or \
         (user == 'scissors' and bot_choice == 'paper'):
        result, react = "You win 😏", "😤"
    else:
        result, react = "I win! 😌", "🎉"
    
    reply = f"<b>✂️ RPS</b>\n\nYou: {user}\nMe: {bot_choice}\n\n{result} {react}"
    bot.reply_to(message, reply, parse_mode="HTML")
    add_to_history(message.from_user.id, f"played {user}", reply)

# ================== DEFINE HANDLER ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith('define '))
def handle_define(message):
    if not is_user_verified(message.from_user.id) or message.message_id in processed_messages:
        return
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    try:
        word = message.text.split(' ', 1)[1].strip()
        if not word:
            bot.reply_to(message, "Define what? 🙄")
            return
        
        mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
        
        # 🔥 TYPING EFFECT
        bot.send_chat_action(message.chat.id, 'typing')
        
        r = requests.get(f'https://api.dictionaryapi.dev/api/v2/entries/en/{word}', timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            definition = data[0]['meanings'][0]['definitions'][0]['definition']
            reply = f"<b>📖 {word.upper()}</b>\n\n{definition}"
            bot.reply_to(message, reply, parse_mode="HTML")
            add_to_history(message.from_user.id, f"define {word}", reply)
        else:
            reply = f"'{word}'? Never heard of it. 🙄"
            bot.reply_to(message, reply)
            add_to_history(message.from_user.id, f"define {word}", reply)
    except Exception as e:
        print(f"Define error: {e}")
        bot.reply_to(message, "That word doesn't exist... or reality. 😏")

# ================== TRANSLATE HANDLER ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith('translate '))
def handle_translate(message):
    if not is_user_verified(message.from_user.id) or message.message_id in processed_messages:
        return
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    try:
        parts = message.text.split(' ', 3)
        if len(parts) < 4:
            bot.reply_to(message, "Use: translate en fr Hello")
            return
        
        _, from_lang, to_lang, text = parts
        from_lang, to_lang = from_lang[:2].lower(), to_lang[:2].lower()
        
        if not text.strip():
            return
        
        mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
        
        # 🔥 TYPING EFFECT
        bot.send_chat_action(message.chat.id, 'typing')
        
        translated = GoogleTranslator(source=from_lang, target=to_lang).translate(text)
        reply = f"<b>🌍 TRANSLATION</b>\n\n{translated}"
        bot.reply_to(message, reply, parse_mode="HTML")
        add_to_history(message.from_user.id, f"translate {text[:30]}...", reply)
    except Exception as e:
        print(f"Translate error: {e}")
        bot.reply_to(message, "Translation failed 😒")

# ================== AI HANDLER ==================
def ask_groq(prompt, user_id=None):
    if not GROQ_KEY or GROQ_KEY == "your_groq_api_key_here":
        return None
    
    context = get_conversation_context(user_id) if user_id else ""
    
    system_prompt = (
        "You are Miss Tristin, a 20-year-old American girl. "
        "Keep responses under 150 characters. Be brief and sassy. "
        "Never mention being AI. Use emojis sparingly. "
        "Be casual and conversational like a real person."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({"role": "system", "content": f"Recent conversation:\n{context}"})
    messages.append({"role": "user", "content": prompt[:200]})
    
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.8, "max_tokens": 100},
            timeout=12
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"Groq API error: {r.status_code}")
    except Exception as e:
        print(f"Groq API exception: {e}")
    return None

def process_ai_request(user_msg, user_id, first_name, chat_id, msg_obj, is_mention=False):
    if not user_msg or len(user_msg.strip()) == 0:
        if is_mention:
            reply = f"Yeah? 👀"
            bot.reply_to(msg_obj, reply)
            add_to_history(user_id, "[empty mention]", reply)
        return
    
    expanded = expand_acronyms(user_msg)
    
    # Check common responses
    common = get_common_response(expanded)
    if common:
        bot.reply_to(msg_obj, common)
        add_to_history(user_id, user_msg, common)
        return
    
    # 🔥 TYPING EFFECT - Show "typing..." while generating response
    bot.send_chat_action(chat_id, 'typing')
    
    # Try Groq
    reply = ask_groq(expanded, user_id)
    
    if not reply:
        if is_mention:
            fallbacks = [f"Yeah? 👀", f"What's up? 😏", f"I'm listening... 💁‍♀️",
                        f"You called? 😌", f"Hmm? 💅", f"idk, what's good? 🤔"]
        else:
            fallbacks = [f"Say that again? 😏", f"Interesting... 😌", f"Go on... 👀",
                        f"Yeah? 💁‍♀️", f"Uh huh... 💅", f"idk, what's good? 🤔"]
        reply = random.choice(fallbacks)
    
    bot.reply_to(msg_obj, reply)
    add_to_history(user_id, user_msg, reply)

# ================== CHAT HANDLER ==================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_chat(message):
    if message.text.startswith('/'):
        return
    if not is_user_verified(message.from_user.id):
        return
    if message.message_id in processed_messages:
        return
    
    ensure_user_exists(message.from_user.id)
    
    should_respond = False
    is_mention = False
    clean_msg = message.text
    
    # Private chat
    if message.chat.type == 'private':
        should_respond = True
        is_mention = True
    # @mention
    elif f"@{BOT_USERNAME}".lower() in message.text.lower():
        should_respond = True
        is_mention = True
        clean_msg = re.sub(re.escape(f"@{BOT_USERNAME}"), '', message.text, flags=re.IGNORECASE).strip()
    # Reply to bot
    elif message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot_info.id:
            should_respond = True
            is_mention = True
    # Name triggers
    elif any(t in message.text.lower() for t in ['tristin', 'derieri', 'miss tristin']):
        should_respond = True
        is_mention = True
        clean_msg = message.text
        for t in ['tristin', 'derieri', 'miss tristin']:
            clean_msg = re.sub(re.escape(t), '', clean_msg, flags=re.IGNORECASE).strip()
    
    if not should_respond:
        return
    if not can_send_response(message.from_user.id, message.chat.id, message.message_id):
        return
    
    mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
    process_ai_request(clean_msg, message.from_user.id, message.from_user.first_name,
                      message.chat.id, message, is_mention)

# ================== UNSUPPORTED CONTENT ==================
@bot.message_handler(content_types=['audio', 'document', 'photo', 'sticker', 'video', 'voice', 'location', 'contact'])
def handle_unsupported(message):
    if not is_user_verified(message.from_user.id) or message.message_id in processed_messages:
        return
    if can_send_response(message.from_user.id, message.chat.id, message.message_id):
        mark_response_sent(message.from_user.id, message.chat.id, message.message_id)
        
        # 🔥 TYPING EFFECT
        bot.send_chat_action(message.chat.id, 'typing')
        time.sleep(0.2)
        
        roasts = [f"Text only, {message.from_user.first_name}. 😏",
                 f"Use your words... I know you have them. 😌",
                 f"Nice try. Now type something. 😑"]
        reply = random.choice(roasts)
        bot.reply_to(message, reply)
        add_to_history(message.from_user.id, "[non-text]", reply)

# ================== FLASK SERVER ==================
app = Flask(__name__)

@app.route('/')
def home():
    seconds = int(time.time() - START_TIME)
    days, rem = divmod(seconds, 86400)
    hours, mins = divmod(rem, 3600)
    minutes = mins // 60
    uptime = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"
    
    return jsonify({
        'status': 'alive',
        'bot': 'Miss Tristin 💅',
        'username': f"@{BOT_USERNAME}",
        'uptime': uptime,
        'users': len(users_data),
        'verified': len(verified_users),
        'conversations': len(conversation_history)
    })

@app.route('/ping')
def ping():
    return jsonify({'pong': True, 'timestamp': time.time()})

# ================== RUN BOT ==================
def run_bot_polling():
    """Run bot polling with auto-reconnect"""
    while True:
        try:
            print("🚀 Bot polling started...")
            bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Bot crashed: {e}")
            print("🔄 Restarting in 5 seconds...")
            time.sleep(5)
            continue

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🔥 MISS TRISTIN IS AWAKE 🔥")
    print(f"🤖 @{BOT_USERNAME}")
    print(f"🌍 Render: {'Yes' if IS_RENDER else 'No'}")
    print("="*50)
    print(f"📊 Users: {len(users_data)}")
    print(f"✅ Verified: {len(verified_users)}")
    print(f"💬 Conversations: {len(conversation_history)}")
    print("="*50 + "\n")

    # Save initial data
    save_all_data()

    # Start bot polling in a thread
    bot_thread = threading.Thread(target=run_bot_polling, daemon=True)
    bot_thread.start()
    print("🚀 Bot thread started with TYPING EFFECT enabled 💬")

    # Start Flask server
    print(f"🌐 Starting Flask server on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
