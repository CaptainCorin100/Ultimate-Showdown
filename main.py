from typing import Final
import os
from dotenv import load_dotenv
from discord import Intents, Client, Message, app_commands, User, Button, ButtonStyle, Interaction
from discord.ext import commands
from discord.ui import *
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
    flag = any(x.get("user_id") == player.id for x in private_channels)
    if flag:
        confirm_button = Button(label="Confirm", style=ButtonStyle.green)
        cancel_button = Button(label="Cancel", style=ButtonStyle.danger)

        async def confirm_button_callback (interaction:Interaction):
            nonlocal private_channels
            remove_filter = filter(lambda x: x.get("user_id") == player.id, private_channels)
            for x in remove_filter:
                private_channels.remove(x)
            private_channels.append({"user_id":player.id,"channel_id":interaction.channel.id})

            await interaction.response.edit_message(content="Channel has been updated successfully!", view=None)
            print(global_data)

        async def cancel_button_callback (interaction:Interaction):
            confirm_button.disabled = True
            cancel_button.disabled = True
            await interaction.response.edit_message(content="Cancelled.", view=None)

        confirm_button.callback = confirm_button_callback
        cancel_button.callback = cancel_button_callback

        view = View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)

        await ctx.send(f"{player.display_name} already has a private channel! Would you like to change it to this one?", view=view)
    else:
        private_channels.append({"user_id":player.id,"channel_id":ctx.channel.id})
        msg = await ctx.send(f"Welcome, {player.display_name}, to your private channel!")

@bot.hybrid_command(name="clear_private_channel", description="Clears the private channel for a player.")
async def clear_private_channel (ctx: commands.Context, player:User) -> None:
    private_channels = global_data.get("private_channels")
    remove_filter = filter(lambda x: x.get("user_id") == player.id, private_channels)
    count = 0
    for y in remove_filter:
        private_channels.remove(y) 
        count += 1
    if count == 0:
        await ctx.send(f"{player.display_name} does not have a private channel set.")
    else:
        await ctx.send(f"{player.display_name}'s private channel has been cleared.")


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
