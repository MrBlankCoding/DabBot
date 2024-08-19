from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf.csrf import CSRFProtect
import discord
from discord.ext import commands
import threading
import asyncio
import os
import logging
from queue import Queue
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key')
csrf = CSRFProtect(app)

# File upload configurations
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Make sure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not set in environment variables")

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables
channel_id = None
user_id = None
dm_mode = False
censor_enabled = True
ready_event = asyncio.Event()
received_messages = Queue()
error_messages = Queue()

@bot.event
async def on_ready():
    logger.info(f'Bot is ready. Logged in as {bot.user}')
    ready_event.set()

@bot.event
async def on_message(message):
    if dm_mode and message.guild is None and message.author != bot.user:
        logger.info(f"Received DM from {message.author}: {message.content}")
        received_messages.put((message.author.name, message.content))
    await bot.process_commands(message)

def load_swear_words(file_path):
    with open(file_path, 'r') as file:
        return [word.strip().lower() for word in file]

def censor_swear_words(text, swear_words, censor_enabled=True):
    if not censor_enabled:
        return text
    
    text_lower = text.lower()
    
    for word in swear_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        text_lower = re.sub(pattern, '*' * len(word), text_lower)
    
    censored_text = ''.join('*' if censored_char == '*' else original_char 
                            for original_char, censored_char in zip(text, text_lower))
    
    return censored_text

async def send_channel_message(channel_id, message, file_path=None, reply_to=None):
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            raise ValueError(f"Channel with ID {channel_id} not found.")
        
        censored_message = censor_swear_words(message)
        
        kwargs = {}
        if file_path:
            kwargs['file'] = discord.File(file_path)
        
        if reply_to:
            try:
                reply_message = await channel.fetch_message(int(reply_to))
                kwargs['reference'] = reply_message
            except discord.NotFound:
                logger.warning(f"Message to reply to (ID: {reply_to}) not found.")

        await channel.send(censored_message, **kwargs)
        
        if file_path:
            os.remove(file_path)  # Clean up the file after sending
    except discord.errors.HTTPException as e:
        error_msg = f"Failed to send message: {e}"
        logger.error(error_msg)
        error_messages.put(error_msg)
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        error_messages.put(error_msg)

async def send_dm(user_id, message, file_path=None, reply_to=None):
    try:
        user = await bot.fetch_user(user_id)
        if user is None:
            raise ValueError(f"User with ID {user_id} not found.")
        
        censored_message = censor_swear_words(message)
        
        kwargs = {}
        if file_path:
            kwargs['file'] = discord.File(file_path)
        
        if reply_to:
            try:
                reply_message = await user.fetch_message(int(reply_to))
                kwargs['reference'] = reply_message
            except discord.NotFound:
                logger.warning(f"Message to reply to (ID: {reply_to}) not found.")

        await user.send(censored_message, **kwargs)
        
        if file_path:
            os.remove(file_path)  # Clean up the file after sending
    except discord.errors.HTTPException as e:
        error_msg = f"Failed to send DM: {e}"
        logger.error(error_msg)
        error_messages.put(error_msg)
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        error_messages.put(error_msg)

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(TOKEN))

@app.route('/', methods=['GET', 'POST'])
def index():
    global channel_id, user_id, dm_mode
    if request.method == 'POST':
        channel_id = int(request.form['channel_id']) if request.form['channel_id'] else None
        user_id = int(request.form['user_id']) if request.form['user_id'] else None
        dm_mode = 'dm_mode' in request.form

        flash('Settings updated successfully!', 'success')
        return redirect(url_for('index'))
    
    messages = []
    while not received_messages.empty():
        messages.append(received_messages.get())
    
    errors = []
    while not error_messages.empty():
        errors.append(error_messages.get())

    return render_template('index.html', channel_id=channel_id, user_id=user_id, 
                           dm_mode=dm_mode, received_messages=messages, errors=errors,
                           censor_enabled=censor_enabled)

@app.route('/send_message', methods=['POST'])
@csrf.exempt
def send_message():
    global channel_id, user_id, dm_mode
    message = request.form['message']
    reply_to = request.form.get('reply_to')
    
    if not message and 'file' not in request.files:
        flash('Message or file must be provided!', 'error')
        return redirect(url_for('index'))

    file = request.files.get('file')
    file_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

    if dm_mode and user_id:
        asyncio.run_coroutine_threadsafe(send_dm(user_id, message, file_path, reply_to), bot.loop)
    elif channel_id:
        asyncio.run_coroutine_threadsafe(send_channel_message(channel_id, message, file_path, reply_to), bot.loop)
    else:
        flash('Please set a channel ID or user ID and enable DM mode.', 'error')
    
    return redirect(url_for('index'))

@app.route('/toggle_censor', methods=['POST'])
@csrf.exempt
def toggle_censor():
    global censor_enabled
    censor_enabled = not censor_enabled
    flash(f'Censoring is now {"enabled" if censor_enabled else "disabled"}', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    swear_words_file = 'badwords.txt'
    swear_words = load_swear_words(swear_words_file)
    logger.info("Starting Discord bot")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    logger.info("Starting Flask application")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
