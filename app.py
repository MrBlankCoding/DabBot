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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key')
csrf = CSRFProtect(app)

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

async def send_channel_message(channel_id, message):
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            raise ValueError(f"Channel with ID {channel_id} not found.")
        await channel.send(message)
    except discord.errors.HTTPException as e:
        error_msg = f"Failed to send message: {e}"
        logger.error(error_msg)
        error_messages.put(error_msg)
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        error_messages.put(error_msg)

async def send_dm(user_id, message):
    try:
        user = await bot.fetch_user(user_id)
        if user is None:
            raise ValueError(f"User with ID {user_id} not found.")
        await user.send(message)
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
                           dm_mode=dm_mode, received_messages=messages, errors=errors)

@app.route('/send_message', methods=['POST'])
@csrf.exempt
def send_message():
    global channel_id, user_id, dm_mode
    message = request.form['message']
    
    if not message:
        flash('Message cannot be empty!', 'error')
        return redirect(url_for('index'))

    if dm_mode and user_id:
        asyncio.run_coroutine_threadsafe(send_dm(user_id, message), bot.loop)
    elif channel_id:
        asyncio.run_coroutine_threadsafe(send_channel_message(channel_id, message), bot.loop)
    else:
        flash('Please set a channel ID or user ID and enable DM mode.', 'error')
    
    return redirect(url_for('index'))

# Initialize the bot in a separate thread
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

# Wait for the bot to be ready
asyncio.get_event_loop().run_until_complete(ready_event.wait())