from flask import Flask, render_template, request, redirect, url_for
import discord
from discord.ext import commands
import threading
import asyncio

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

# Create an asyncio Event to wait for the bot to be ready
ready_event = asyncio.Event()

# List to store received messages
received_messages = []

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')
    ready_event.set()

@bot.event
async def on_message(message):
    if dm_mode and message.guild is None and message.author != bot.user:
        print(f"Received DM from {message.author}: {message.content}")
        received_messages.append((message.author.name, message.content))

async def send_channel_message(channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel is None:
        print(f"Error: Channel with ID {channel_id} not found.")
    elif isinstance(channel, discord.TextChannel):  # Check if it's a text channel
        await channel.send(message)
    else:
        print(f"Error: Channel with ID {channel_id} is not a text channel.") 

async def send_dm(user_id, message):
    user = await bot.fetch_user(user_id)
    if user is None:
        print(f"Error: User with ID {user_id} not found.")
    else:
        await user.send(message)

def run_bot(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(TOKEN))

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
        future = asyncio.run_coroutine_threadsafe(send_dm(user_id, message), shared_loop)
        future.result()  # Wait for the coroutine to complete
    elif channel_id:
        future = asyncio.run_coroutine_threadsafe(send_channel_message(channel_id, message), shared_loop)
        future.result()  # Wait for the coroutine to complete
    return redirect(url_for('index'))

if __name__ == "__main__":
    global shared_loop  # Declare shared_loop as global
    shared_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(shared_loop)

    bot_thread = threading.Thread(target=run_bot, args=(shared_loop,))
    bot_thread.start()

    app.run(host='0.0.0.0', port=5001)
