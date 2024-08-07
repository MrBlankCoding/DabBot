from flask import Flask, render_template, request, redirect, url_for
import discord
from discord.ext import commands
import threading
import asyncio
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables for channel ID and user ID
channel_id = None
user_id = None

# Set DM mode (True to send DMs, False to send to a channel)
dm_mode = False

# List to store received messages
received_messages = []

# Create an event loop for async operations
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

@bot.event
async def on_ready():
    logger.info(f'Bot is ready. Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if dm_mode and message.guild is None and message.author != bot.user:
        logger.info(f"Received DM from {message.author}: {message.content}")
        received_messages.append((message.author.name, message.content))

async def send_channel_message(channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel is None:
        logger.error(f"Error: Channel with ID {channel_id} not found.")
    elif isinstance(channel, discord.TextChannel):
        await channel.send(message)
    else:
        logger.error(f"Error: Channel with ID {channel_id} is not a text channel.")

async def send_dm(user_id, message):
    user = await bot.fetch_user(user_id)
    if user is None:
        logger.error(f"Error: User with ID {user_id} not found.")
    else:
        await user.send(message)

def run_bot():
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN environment variable is not set!")
        return

    try:
        logger.info("Starting bot...")
        asyncio.run(bot.start(token))
    except Exception as e:
        logger.exception(f"Error running bot: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    global channel_id, user_id, dm_mode
    if request.method == 'POST':
        channel_id = int(request.form['channel_id']) if request.form['channel_id'] else None
        user_id = int(request.form['user_id']) if request.form['user_id'] else None
        dm_mode = 'dm_mode' in request.form
        return redirect(url_for('index'))
    return render_template('index.html', channel_id=channel_id, user_id=user_id, dm_mode=dm_mode, received_messages=received_messages)

@app.route('/send_message', methods=['POST'])
def send_message():
    global channel_id, user_id, dm_mode
    message = request.form['message']
    if dm_mode and user_id:
        asyncio.run_coroutine_threadsafe(send_dm(user_id, message), loop)
    elif channel_id:
        asyncio.run_coroutine_threadsafe(send_channel_message(channel_id, message), loop)
    return redirect(url_for('index'))

if __name__ == "__main__":
    logger.info("Starting application...")
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    logger.info("Bot thread started")

    try:
        logger.info("Starting Flask app...")
        app.run(host='0.0.0.0', port=5001)
    except Exception as e:
        logger.exception(f"Error running Flask app: {e}")
