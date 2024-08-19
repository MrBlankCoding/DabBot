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
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField
from wtforms.validators import DataRequired

class SettingsForm(FlaskForm):
    channel_id = StringField('Channel ID', validators=[DataRequired()])
    user_id = StringField('User ID', validators=[DataRequired()])
    dm_mode = BooleanField('DM Mode')
    submit = SubmitField('Update Settings')

class MessageForm(FlaskForm):
    message = StringField('Message', validators=[DataRequired()])
    submit = SubmitField('Send Message')

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
    settings_form = SettingsForm()
    message_form = MessageForm()

    if settings_form.validate_on_submit():
        channel_id = int(settings_form.channel_id.data) if settings_form.channel_id.data else None
        user_id = int(settings_form.user_id.data) if settings_form.user_id.data else None
        dm_mode = settings_form.dm_mode.data
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('index'))
    
    messages = []
    while not received_messages.empty():
        messages.append(received_messages.get())
    
    errors = []
    while not error_messages.empty():
        errors.append(error_messages.get())

    return render_template('index.html', settings_form=settings_form, message_form=message_form,
                           channel_id=channel_id, user_id=user_id, 
                           dm_mode=dm_mode, received_messages=messages, errors=errors)

@app.route('/send_message', methods=['POST'])
def send_message():
    global channel_id, user_id, dm_mode
    form = MessageForm()
    
    if form.validate_on_submit():
        message = form.message.data
        
        if dm_mode and user_id:
            asyncio.run_coroutine_threadsafe(send_dm(user_id, message), bot.loop)
        elif channel_id:
            asyncio.run_coroutine_threadsafe(send_channel_message(channel_id, message), bot.loop)
        else:
            flash('Please set a channel ID or user ID and enable DM mode.', 'error')
    else:
        flash('Invalid form submission.', 'error')
    
    return redirect(url_for('index'))

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(TOKEN))
    
if __name__ == '__main__':
    logger.info("Starting Discord bot")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    logger.info("Starting Flask application")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
