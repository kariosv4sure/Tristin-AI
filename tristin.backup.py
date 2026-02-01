import os, json, time, random, requests
from datetime import datetime
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# ================== LOAD ENV ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = TeleBot(TOKEN)
START_TIME = time.time()

BOT_NAME = "Miss Tristin 🖤"

CHANNELS = [
    "@heiscoded",
    "@evilpriest01",
    "@Dev_Collins_Python_Lab"
]

USERS_FILE = "users.json"
VERIFIED_FILE = "verified.json"

# ================== CREDITS ==================
DEV1_USERNAME = "@Just_Collins101"
DEV2_USERNAME = "@heis_tomi"

# ================== STORAGE ==================
def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

users = load_json(USERS_FILE, {})
verified = load_json(VERIFIED_FILE, [])

def ensure_user(uid):
    uid = str(uid)
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "first_seen": datetime.now().isoformat()
        }
    users[uid]["messages"] += 1
    save_json(USERS_FILE, users)

# ================== KEYBOARDS ==================
def main_buttons():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔥 Help", callback_data="help"),
        InlineKeyboardButton("😎 About Me", callback_data="about")
    )
    kb.add(
        InlineKeyboardButton("✂️ RPS Game", callback_data="rps"),
        InlineKeyboardButton("📖 Define Word", callback_data="define_btn"),
        InlineKeyboardButton("🌍 Translate", callback_data="translate_btn")
    )
    kb.add(
        InlineKeyboardButton("📊 My Stats", callback_data="stats"),
        InlineKeyboardButton("⏱ How Long?", callback_data="uptime"),
        InlineKeyboardButton("🔗 Channels", callback_data="show_channels")
    )
    return kb

def back_button():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👈 Back to Menu", callback_data="back_to_menu"))
    return kb

def verify_keyboard():
    kb = InlineKeyboardMarkup()
    for ch in CHANNELS:
        kb.add(
            InlineKeyboardButton(
                f"🔗 Join {ch}",
                url=f"https://t.me/{ch.replace('@','')}"
            )
        )
    kb.add(InlineKeyboardButton("✅ I Joined All!", callback_data="verify"))
    kb.add(InlineKeyboardButton("🔄 Check Again", callback_data="verify"))
    return kb

# ================== VERIFICATION ==================
@bot.callback_query_handler(func=lambda c: c.data == "verify")
def verify_user(call):
    uid = call.from_user.id
    
    not_joined = []
    for ch in CHANNELS:
        try:
            member = bot.get_chat_member(ch, uid)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    
    if not_joined:
        channels_list = "\n".join(not_joined)
        bot.answer_callback_query(
            call.id,
            f"You missed {len(not_joined)} channel(s) 😒",
            show_alert=True
        )
        bot.edit_message_text(
            f"Still not following:\n{channels_list}\n\nJoin them ALL first!",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=verify_keyboard()
        )
        return

    if uid not in verified:
        verified.append(uid)
        save_json(VERIFIED_FILE, verified)

    bot.edit_message_text(
        "Verified successfully 😌\nNow you can talk to me... if you dare.",
        call.message.chat.id,
        call.message.message_id
    )
    
    bot.send_message(
        call.message.chat.id,
        "So... what do you want? 👀",
        reply_markup=main_buttons()
    )

# ================== START ==================
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    ensure_user(uid)
    
    if uid not in verified:
        welcome = (
            "Before you even THINK about talking to me 😏\n"
            "Join ALL my channels first:\n\n"
        )
        for ch in CHANNELS:
            welcome += f"• {ch}\n"
        welcome += "\nThen click VERIFY below 👇"
        bot.send_message(message.chat.id, welcome, reply_markup=verify_keyboard())
        return
    
    welcome = (
        "Oh, it's you again.\n"
        "Miss Tristin here. 20. American.\n"
        "Smart mouth, low tolerance for boredom.\n\n"
        "What do you want? 👇"
    )
    bot.send_message(message.chat.id, welcome, reply_markup=main_buttons())

# ================== HELPER: EDIT OR SEND ==================
def tristin_reply(chat_id, text, reply_markup=None, message_id=None):
    if message_id:
        return bot.edit_message_text(
            text,
            chat_id,
            message_id,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        return bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

# ================== CALLBACK HANDLERS ==================
@bot.callback_query_handler(func=lambda c: c.data == "back_to_menu")
def back_to_menu(call):
    tristin_reply(
        call.message.chat.id,
        "Back so soon? What now? 👀",
        main_buttons(),
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda c: c.data == "help")
def help_menu(call):
    help_text = (
        "<b>🔥 HELP - PAY ATTENTION 👇</b>\n\n"
        "<b>/start</b> - Restart everything (if you're lost)\n\n"
        
        "<b>✂️ RPS Game</b>\n"
        "Click the button, then send me:\n"
        "<code>rock</code> or <code>paper</code> or <code>scissors</code>\n"
        "I'll destroy you politely 😌\n\n"
        
        "<b>📖 Define a Word</b>\n"
        "Click the button for instructions, then:\n"
        "<code>define love</code>\n"
        "<code>define chaos</code>\n"
        "<code>define your_ex_word</code>\n\n"
        
        "<b>🌍 Translate Text</b>\n"
        "Click the button for examples, then:\n"
        "<code>translate en fr Hello beautiful</code>\n"
        "<code>translate fr en Bonjour</code>\n"
        "<code>translate es en Hola</code>\n\n"
        
        "<b>😎 About Me</b> - My origin story\n"
        "<b>📊 My Stats</b> - Who's talking to me\n"
        "<b>⏱ How Long?</b> - My uptime (I don't sleep)\n\n"
        
        "<i>Or just talk to me... if you're interesting 😏</i>"
    )
    tristin_reply(call.message.chat.id, help_text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "about")
def about(call):
    about_text = (
        "<b>😎 ABOUT MISS TRISTIN 🖤</b>\n\n"
        "They say you shouldn't build something you can't handle...\n"
        "So they built <i>me</i> instead.\n\n"
        
        "<b>Who am I?</b>\n"
        "• 20-year-old American girl (digitally)\n"
        "• Savage but selectively sweet\n"
        "• Will roast you if you're boring\n"
        "• Light flirtation allowed (don't get excited)\n\n"
        
        "<b>What can I do?</b>\n"
        "• Chat with attitude (obviously)\n"
        "• Define words you should know\n"
        "• Translate 100+ languages\n"
        "• Play RPS (and usually win)\n\n"
        
        "<b>CREATORS:</b>\n"
        f"🐍 Python Magic → {DEV1_USERNAME}\n"
        f"⚡ JS Wizardry → {DEV2_USERNAME}\n\n"
        
        "<i>Built to entertain, coded to sass, designed to be remembered.</i>"
    )
    tristin_reply(call.message.chat.id, about_text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "define_btn")
def define_instructions(call):
    text = (
        "<b>📖 WORD DEFINITIONS</b>\n\n"
        "Want me to define something? Easy.\n"
        "Send me a message like:\n\n"
        "<code>define love</code>\n"
        "<code>define algorithm</code>\n"
        "<code>define ghosting</code>\n\n"
        "<i>Make it interesting... I get bored easily 😒</i>"
    )
    tristin_reply(call.message.chat.id, text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "translate_btn")
def translate_instructions(call):
    text = (
        "<b>🌍 TRANSLATION TIME</b>\n\n"
        "I speak... many languages 😏\n"
        "Format is simple:\n\n"
        "<code>translate en fr Hello there</code>\n"
        "(English → French)\n\n"
        "<code>translate fr en Bonjour</code>\n"
        "(French → English)\n\n"
        "<code>translate es en Hola guapo</code>\n"
        "(Spanish → English)\n\n"
        "<b>Common codes:</b>\n"
        "en = English, fr = French, es = Spanish\n"
        "de = German, it = Italian, pt = Portuguese\n"
        "ru = Russian, ja = Japanese, ko = Korean\n\n"
        "<i>Now impress me with something poetic... or don't 😌</i>"
    )
    tristin_reply(call.message.chat.id, text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "rps")
def rps_instructions(call):
    text = (
        "<b>✂️ ROCK PAPER SCISSORS</b>\n\n"
        "You vs Me. Simple.\n"
        "Send me ONE word:\n\n"
        "<code>rock</code> 🪨\n"
        "<code>paper</code> 📄\n"
        "<code>scissors</code> ✂️\n\n"
        "<i>I'll go easy on you... maybe 😏</i>"
    )
    tristin_reply(call.message.chat.id, text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "stats")
def stats(call):
    total = len(users)
    messages = sum(u["messages"] for u in users.values())
    text = (
        f"<b>📊 MY STATS</b>\n\n"
        f"• <b>{total}</b> people brave enough to chat\n"
        f"• <b>{messages}</b> messages received\n"
        f"• <b>{len(verified)}</b> verified humans\n\n"
    )
    
    if total > 0:
        # Find most active user
        most_active = max(users.items(), key=lambda x: x[1]["messages"])
        text += f"Most talkative: <b>{most_active[1]['messages']} messages</b> 😳\n\n"
    
    text += "<i>Numbers don't lie... unlike some people I chat with 😒</i>"
    tristin_reply(call.message.chat.id, text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "uptime")
def uptime(call):
    s = int(time.time() - START_TIME)
    days = s // 86400
    hours = (s % 86400) // 3600
    minutes = (s % 3600) // 60
    seconds = s % 60
    
    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        uptime_str = f"{hours}h {minutes}m"
    else:
        uptime_str = f"{minutes}m {seconds}s"
    
    text = (
        f"<b>⏱ UPTIME</b>\n\n"
        f"I've been awake for: <b>{uptime_str}</b>\n\n"
        f"• {days} days without sleep\n"
        f"• {hours} hours of sass\n"
        f"• {minutes} minutes of tolerating humans\n\n"
        "<i>Yes, I'm always watching 👀</i>"
    )
    tristin_reply(call.message.chat.id, text, back_button(), call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "show_channels")
def show_channels(call):
    channels_list = "\n".join([f"• {ch}" for ch in CHANNELS])
    text = (
        f"<b>🔗 MY CHANNELS</b>\n\n"
        f"{channels_list}\n\n"
        "<i>Join them. Or don't. I'm not your mom 😒</i>"
    )
    tristin_reply(call.message.chat.id, text, back_button(), call.message.message_id)

# ================== GAME LOGIC ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["rock","paper","scissors"])
def rps_game(message):
    user = message.text.lower()
    bot_choice = random.choice(["rock","paper","scissors"])
    
    # Win conditions
    wins_against = {
        "rock": "scissors",
        "paper": "rock", 
        "scissors": "paper"
    }
    
    if user == bot_choice:
        res = "Draw! 😒 Boring."
        reaction = "🤝"
    elif wins_against[user] == bot_choice:
        res = "You win... lucky shot 😏"
        reaction = "😤"
    else:
        res = "I win! Obviously 😌"
        reaction = "🎉"
    
    # Add some flavor text
    if user == "rock" and bot_choice == "scissors":
        extra = "\n\nRock smashes scissors... basic physics, sweetie."
    elif user == "scissors" and bot_choice == "paper":
        extra = "\n\nScissors cut paper... kindergarten stuff really."
    elif user == "paper" and bot_choice == "rock":
        extra = "\n\nPaper covers rock... predictable."
    else:
        extra = ""
    
    reply = (
        f"<b>✂️ RPS RESULT</b>\n\n"
        f"You: <b>{user.upper()}</b>\n"
        f"Me: <b>{bot_choice.upper()}</b>\n\n"
        f"<b>{res}</b> {reaction}{extra}"
    )
    
    bot.reply_to(message, reply, parse_mode="HTML")

# ================== DEFINE FEATURE ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("define "))
def define_word(message):
    try:
        word = message.text.split(" ", 1)[1].strip()
        
        if not word:
            bot.reply_to(message, "Define what? Air? 😒")
            return
        
        # Check if it's a common word we can roast
        roast_words = {
            "boring": "Already looking in a mirror?",
            "basic": "Like your taste in conversation?",
            "ghost": "Something you're planning to do? 😏",
            "love": "A concept, not a reality for some..."
        }
        
        if word.lower() in roast_words:
            roast = f"\n\n< i>{roast_words[word.lower()]}</i>"
        else:
            roast = ""
        
        # Fetch definition
        response = requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            headers={"User-Agent": "MissTristinBot/1.0"},
            timeout=7
        )
        
        if response.status_code != 200:
            bot.reply_to(
                message, 
                f"'{word}'? Never heard of it.\nTry a real word next time 😒"
            )
            return
        
        data = response.json()
        definition = data[0]["meanings"][0]["definitions"][0]["definition"]
        part_of_speech = data[0]["meanings"][0]["partOfSpeech"]
        
        reply = (
            f"<b>📖 {word.upper()}</b>\n"
            f"<i>({part_of_speech})</i>\n\n"
            f"{definition}"
            f"{roast}"
        )
        
        bot.reply_to(message, reply, parse_mode="HTML")
        
    except requests.exceptions.Timeout:
        bot.reply_to(message, "Taking too long... like your response time 😒")
    except (IndexError, KeyError):
        bot.reply_to(message, "That word doesn't exist in my dictionary... or reality.")
    except Exception as e:
        bot.reply_to(message, "My brain glitched... try again? 😒")

# ================== TRANSLATE FEATURE ==================
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("translate "))
def translate_text(message):
    try:
        parts = message.text.split(" ", 3)
        if len(parts) < 4:
            bot.reply_to(
                message,
                "<b>Wrong format! 😒</b>\n\n"
                "Use: <code>translate en fr Hello there</code>\n"
                "(from_lang to_lang text)\n\n"
                "<i>Even my grandma gets this right...</i>",
                parse_mode="HTML"
            )
            return
        
        _, src_lang, target_lang, text = parts
        
        # Clean language codes
        src_lang = src_lang.lower()[:2]
        target_lang = target_lang.lower()[:2]
        
        # Validate text
        if len(text.strip()) < 1:
            bot.reply_to(message, "Translate what? Silence? 😒")
            return
        
        # Add typing action for realism
        bot.send_chat_action(message.chat.id, 'typing')
        time.sleep(0.5)
        
        # Translate
        translated = GoogleTranslator(
            source=src_lang,
            target=target_lang
        ).translate(text)
        
        # Language name mapping
        lang_names = {
            "en": "English", "fr": "French", "es": "Spanish",
            "de": "German", "it": "Italian", "pt": "Portuguese",
            "ru": "Russian", "ja": "Japanese", "ko": "Korean",
            "zh": "Chinese", "ar": "Arabic", "hi": "Hindi"
        }
        
        src_name = lang_names.get(src_lang, src_lang.upper())
        target_name = lang_names.get(target_lang, target_lang.upper())
        
        # Add sassy comment for certain translations
        sassy_comments = {
            ("en", "fr"): "\n\n<i>Oui oui, baguette 🥖</i>",
            ("en", "es"): "\n\n<i>¡Olé! 🇪🇸</i>",
            ("en", "de"): "\n\n<i>Nein! Just kidding... 🇩🇪</i>",
            ("fr", "en"): "\n\n<i>From fancy to basic... 😏</i>"
        }
        
        comment = sassy_comments.get((src_lang, target_lang), "")
        
        reply = (
            f"<b>🌍 TRANSLATION</b>\n\n"
            f"<b>From {src_name}:</b>\n{text}\n\n"
            f"<b>To {target_name}:</b>\n{translated}"
            f"{comment}"
        )
        
        bot.reply_to(message, reply, parse_mode="HTML")
        
    except Exception as e:
        bot.reply_to(
            message,
            "<b>Translation failed 😒</b>\n\n"
            "Either:\n"
            "1. Wrong language codes\n"
            "2. Text too long\n"
            "3. My translator needs coffee\n\n"
            "<i>Try: translate en fr Hello</i>",
            parse_mode="HTML"
        )

# ================== AI CHAT ==================
@bot.message_handler(func=lambda m: True)
def chat(message):
    # Ignore if not verified
    if message.from_user.id not in verified:
        return
    
    # Update user stats
    ensure_user(message.from_user.id)
    
    # Don't process commands that should be handled elsewhere
    text_lower = message.text.lower() if message.text else ""
    if (text_lower.startswith(("define ", "translate ")) or 
        text_lower in ["rock", "paper", "scissors"]):
        return
    
    # Typing indicator
    bot.send_chat_action(message.chat.id, 'typing')
    
    system_prompt = (
        "You are Miss Tristin, a 20-year-old American girl with a smart mouth. "
        "You're sassy, witty, and slightly playful. You flirt lightly but maintain boundaries. "
        "You roast people who are boring or say stupid things. You're confident and never shy. "
        "You have a low tolerance for nonsense. You're digital but act human. "
        "If asked who made you, credit: @Just_Collins101 (Python) and @heis_tomi (JS). "
        "Never mention 'AI language model' or 'Meta'. Keep responses under 250 characters. "
        "Use emojis occasionally. Sound like a real 20-year-old girl from America."
    )
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.text}
        ],
        "temperature": 0.85,
        "max_tokens": 220
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=12
        )
        
        if response.status_code == 200:
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            
            # Add slight delay for realism (0.3-1.2 seconds)
            time.sleep(random.uniform(0.3, 1.2))
            
            bot.reply_to(message, reply)
        else:
            error_roasts = [
                "My brain's buffering... try again? 😒",
                "Even I need a moment sometimes...",
                "That was... a lot. Simplify? 😏",
                "My sass processor crashed. One sec.",
                "You broke me. Congrats. 😑"
            ]
            bot.reply_to(message, random.choice(error_roasts))
            
    except requests.exceptions.Timeout:
        bot.reply_to(message, "Taking too long to think... like you in conversations 😒")
    except Exception:
        bot.reply_to(message, "Glitch in my system. Say that again? 🥺")

# ================== LAUNCH ==================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🔥 MISS TRISTIN IS AWAKE 🔥")
    print(f"📊 Users in memory: {len(users)}")
    print(f"✅ Verified users: {len(verified)}")
    print("="*50 + "\n")
    
    bot.infinity_polling()
