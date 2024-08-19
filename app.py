from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired
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

class ServerMessageForm(FlaskForm):
    channel_id = StringField('Channel ID', validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Send Message')

class DMMessageForm(FlaskForm):
    user_id = StringField('User ID', validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Send DM')

@bot.event
async def on_ready():
    logger.info(f'Bot is ready. Logged in as {bot.user}')
    ready_event.set()

@bot.event
async def on_message(message):
    if message.guild is None and message.author != bot.user:
        logger.info(f"Received DM from {message.author}: {message.content}")
        received_messages.put((message.author.name, message.content))
    elif message.guild is not None and message.author != bot.user:
        logger.info(f"Received server message from {message.author} in {message.channel}: {message.content}")
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

@app.before_first_request
def initialize_bot():
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Wait for the bot to be ready (with a timeout)
    try:
        asyncio.get_event_loop().run_until_complete(asyncio.wait_for(ready_event.wait(), timeout=60))
    except asyncio.TimeoutError:
        logger.error("Timed out waiting for bot to be ready")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/server', methods=['GET', 'POST'])
def server():
    global channel_id
    form = ServerMessageForm()
    if form.validate_on_submit():
        channel_id = int(form.channel_id.data)
        message = form.message.data
        asyncio.run_coroutine_threadsafe(send_channel_message(channel_id, message), bot.loop)
        flash('Message sent to server!', 'success')
        return redirect(url_for('server'))
    
    messages = []
    while not received_messages.empty():
        author, content = received_messages.get()
        if not dm_mode:
            messages.append((author, content))
    
    errors = []
    while not error_messages.empty():
        errors.append(error_messages.get())

    return render_template('server.html', form=form, channel_id=channel_id, 
                           received_messages=messages, errors=errors)

@app.route('/dm', methods=['GET', 'POST'])
def dm():
    global user_id, dm_mode
    form = DMMessageForm()
    if form.validate_on_submit():
        user_id = int(form.user_id.data)
        message = form.message.data
        dm_mode = True
        asyncio.run_coroutine_threadsafe(send_dm(user_id, message), bot.loop)
        flash('DM sent!', 'success')
        return redirect(url_for('dm'))
    
    messages = []
    while not received_messages.empty():
        author, content = received_messages.get()
        if dm_mode:
            messages.append((author, content))
    
    errors = []
    while not error_messages.empty():
        errors.append(error_messages.get())

    return render_template('dm.html', form=form, user_id=user_id, 
                           received_messages=messages, errors=errors)

if __name__ == '__main__':
    app.run(debug=True)
