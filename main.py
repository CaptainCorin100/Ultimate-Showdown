from typing import Final
import os
from dotenv import load_dotenv
from discord import Intents, Client, Message, app_commands, User
from discord.ext import commands
from random import randint, random, choice
import time
import json
import atexit

#Load token from .env file
load_dotenv()
TOKEN: Final[str] = os.getenv("DISCORD_TOKEN")

#Initialise discord bot settings
intents: Intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

#Initialise JSON
global_data = {
    "private_channels":[]
}


@bot.hybrid_command(name="set_private_channel", description="Sets the private channel for a player.")
async def set_private_channel (ctx: commands.Context, player:User) -> None:
    private_channels = global_data.get("private_channels")
    private_channels.append({"user_id":player.id,"channel_id":ctx.channel.id})
    msg = await ctx.send(f"Welcome, {player.name}, to your private channel!")
    print(global_data)
    


#Sync commands when bot run
@bot.event
async def on_ready() -> None:
    print (f'{bot.user} is now running!')
    await bot.tree.sync()

#Main function
def main() -> None:
    global global_data

    #Load JSON from file
    try:
        with open("data.json", "r") as openfile:
            global_data = json.load(openfile)         
    except OSError:
        print("JSON can't be loaded.")

    #Register to save JSON on quit
    atexit.register(quit)

    #Run the bot
    bot.run(token=TOKEN)

    

def quit() -> None:
    with open("data.json", "w") as writefile:
        json.dump(global_data, writefile)

#Main
if __name__ == "__main__":
    main()
