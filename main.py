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
import networkx as nx

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
        participants = [self.participant1, self.participant2]

        #Iterate between the two participants
        for parti in [self.participant1]:
            #Find the participant's private channel
            channel1_id = next(x for x in global_data.get("private_channels") if x.get("user_id") == parti.id).get("channel_id")
            channel1 = bot.get_channel(channel1_id)

            #Send message in private channel
            participant_view = ContestOptions()
            views.append(participant_view)
            await channel1.send(f"{parti.mention}, you are engaged in a contest in {self.channel.jump_url}.\n How do you respond?", view=participant_view)

        #Schedule to wait until both people have replied
        tasks = []
        for view in views:
            interaction_wait_task = asyncio.create_task(view.wait())
            tasks.append(interaction_wait_task)

        done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        
        #Determine and return the outcome
        outcome = compare_strikes(views[0].strike_type, StrikeType.FORCEFUL)
        outcome_message = ""
        if outcome == None:
            outcome_message = "The round between {} and {} ended in a draw!".format(participants[0].mention, participants[1].mention)
        else:
            outcome_message = "{}'s attack has overpowered {}!".format(participants[outcome].mention, participants[1-outcome].mention)

        return outcome_message


class ContestOptions(View):
    def __init__(self):
        super().__init__()
        self.strike_type = None

    def disable_self (self):
        for child in self.children:
            if type(child) == Button:
                child.disabled = True
        self.stop()

    @button(label="Swift Strike", style=ButtonStyle.primary)
    async def swift_strike (self, interaction: Interaction, button: Button):
        self.disable_self()
        self.strike_type = StrikeType.SWIFT
        await interaction.response.edit_message(content="Interaction submitted.", view=self) 

    @button(label="Forceful Strike", style=ButtonStyle.red)
    async def forceful_strike (self, interaction: Interaction, button: Button):
        self.disable_self()
        self.strike_type = StrikeType.FORCEFUL
        await interaction.response.edit_message(content="Interaction submitted.", view=self)        

    @button(label="Reactive Strike", style=ButtonStyle.gray)
    async def reactive_strike (self, interaction: Interaction, button: Button):
        self.disable_self()
        self.strike_type = StrikeType.REACTIVE
        await interaction.response.edit_message(content="Interaction submitted.", view=self)  
        
        
    
        
class StrikeType(Enum):
    SWIFT = 0
    FORCEFUL = 1
    REACTIVE = 2

#Returns 0, 1, or None depending on which strike wins (or if it is a draw), 
def compare_strikes(strike1:StrikeType, strike2:StrikeType) -> int:
    if strike1 == strike2:
        return None
    #The strikes are ordered such that each one beats the one higher than it
    elif (strike1.value + 1) % 3 == strike2.value:
        return 0
    else:
        return 1


# Runs a contest between two users
@bot.hybrid_command(name="run_contest", description="Runs a contest between two people.")
async def run_contest (ctx: commands.Context, participant1:User, participant2:User) -> None:
    combat_round = CombatRound(participant1, participant2, ctx.channel)
    await ctx.send("Starting contest...")
    for i in range(3):
        msg = await combat_round.start_round()
        await ctx.send(msg)
    

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

class TournamentParticipant:
    def __init__(self, participant:User):
        self.participant = participant
        self.former_challengers = set()
        self.points = 0

class Tournament:
    def __init__(self, participants:list[User]):
        self.tournament_participants:list[TournamentParticipant] = []
        for participant in participants:
            self.tournament_participants.append(TournamentParticipant(participant))
        self.rounds = []

    def create_pairings(self):
        G = nx.Graph()

        G.add_nodes_from(self.tournament_participants)

        for i in range (len(self.tournament_participants)):
            for j in range (i+1, len(self.tournament_participants)):
                if not self.tournament_participants[j] in self.tournament_participants[i].former_challengers:
                    point_diff = abs(self.tournament_participants[j].points - self.tournament_participants[i].points)
                    G.add_edge(self.tournament_participants[j], self.tournament_participants[i], weight=point_diff)

        best_matches:set[tuple[TournamentParticipant]] = nx.algorithms.matching.min_weight_matching(G, "weight")

        name_matches = []
        for pairing in best_matches:
            name_matches.append((pairing[0].participant.display_name, pairing[1].participant.display_name))
        print(name_matches)

@bot.hybrid_command(name="test_tournament", description="Test")
async def test_tournament (ctx: commands.Context, player1:User, player2:User, player3:User, player4:User) -> None:
    tourn = Tournament([player1, player2, player3, player4])
    tourn.create_pairings()

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
