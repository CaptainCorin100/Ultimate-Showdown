from typing import Final
import os
from dotenv import load_dotenv
from discord import Intents, Client, Message, app_commands, User, Button, ButtonStyle, Interaction, TextChannel
from discord.ext import commands
from discord.ui import *
from random import randint, random, choice
import time
import json
import atexit
import asyncio
from enum import Enum

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

#Initialise class for individual combat round
class CombatRound:
    def __init__(self, participant1:User, participant2:User, channel:TextChannel):
        self.participant1 = participant1
        self.participant2 = participant2
        self.channel = channel

    async def start_round(self):
        #Setup the contest options that the participants have access to
        views:list[ContestOptions] = []

        #Iterate between the two participants
        for parti in [self.participant1]:
            #Find the participant's private channel
            channel1_id = next(x for x in global_data.get("private_channels") if x.get("user_id") == parti.id).get("channel_id")
            channel1 = bot.get_channel(channel1_id)

            #Send message in private channel
            participant_view = ContestOptions()
            views.append(participant_view)
            await channel1.send(f"{parti.mention}, you are engaged in a contest in {self.channel.jump_url}.\n How do you respond?", view=participant_view)

        # tasks = [
        #     bot.wait_for("interaction")
        # ]
        # await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

        tasks = []
        for view in views:
            interaction_wait_task = asyncio.create_task(view.wait())
            tasks.append(interaction_wait_task)

        done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        
        print(views[0].strike_type)


class ContestOptions(View):
    def __init__(self):
        super().__init__()
        self.strike_type = None

    @button(label="Swift Strike", style=ButtonStyle.primary)
    async def swift_strike (self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Swift Strike")
        self.strike_type = StrikeType.SWIFT
        self.stop()

    @button(label="Forceful Strike", style=ButtonStyle.red)
    async def forceful_strike (self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Forceful Strike")
        self.strike_type = StrikeType.FORCEFUL
        self.stop()

    @button(label="Reactive Strike", style=ButtonStyle.gray)
    async def reactive_strike (self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Reactive Strike")
        self.strike_type = StrikeType.REACTIVE
        self.stop()    
        
class StrikeType(Enum):
    SWIFT = "swift"
    FORCEFUL = "forceful"
    REACTIVE = "reactive"

# Runs a contest between two users
@bot.hybrid_command(name="run_contest", description="Runs a contest between two people.")
async def run_contest (ctx: commands.Context, participant1:User, participant2:User) -> None:
    combat_round = CombatRound(participant1, participant2, ctx.channel)
    await ctx.send("Starting contest...")
    await combat_round.start_round()
    

#Sets a user's private channel to the one it was called in
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

# Removes a user's current private channel
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
