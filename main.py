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
import numpy as np
import matplotlib.pyplot as plt

#Load token from .env file
load_dotenv()
TOKEN: Final[str] = os.getenv("DISCORD_TOKEN")

#Initialise discord bot settings
intents: Intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

#Initialise JSON
global_data = {
    "private_channels":[],
    "total_rounds":3, #Total number of rounds in the tournament, and number of matches each person can expect to face
    "total_contests":3, #Total number of contests in any given match
    "win_points":2, #Points awarded for winning a contest
    "draw_points":1 #Points awarded for drawing a contest
}

tourn = None


##### Contest commands and classes

#Enum for different types of strike
class StrikeType(Enum):
    SWIFT = 0
    FORCEFUL = 1
    REACTIVE = 2

#Provides a set of buttons to interact with a Contest
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

#Returns 0, 1, or None depending on which strike wins (or if it is a draw), 
def compare_strikes(strike1:StrikeType, strike2:StrikeType) -> int:
    if strike1 == strike2:
        return None
    #The strikes are ordered such that each one beats the one higher than it
    elif (strike1.value + 1) % 3 == strike2.value:
        return 0
    else:
        return 1

async def create_contest(user:User, contest_message:str) -> ContestOptions:
    #Find the participant's private channel
    channel1_id = next(x for x in global_data.get("private_channels") if x.get("user_id") == user.id).get("channel_id")
    channel1 = bot.get_channel(channel1_id)

    #Send message in private channel
    participant_view = ContestOptions()

    await channel1.send(contest_message, view=participant_view)

    return participant_view

##### Match classes and commands

#Initialise class for individual combat match
class CombatMatch:
    def __init__(self, participant1:User, participant2:User, channel:TextChannel):
        self.participants:list[User] = [participant1,participant2]
        self.participant_scores = [0, 0]
        self.channel = channel

    #Generate the message describing the outcome
    def outcome_message(self, outcome) -> str:
        outcome_message = ""
        if outcome == None:
            outcome_message = "The contest between {} and {} ended in a draw!".format(self.participants[0].mention, self.participants[1].mention)
        else:
            outcome_message = "{}'s attack has overpowered {}!".format(self.participants[outcome].mention, self.participants[1-outcome].mention)

        return outcome_message

    #Run the match
    async def run_match(self):
        for i in range(3):
            outcome = await self.run_match_contest()
            msg = self.outcome_message(outcome)
            await self.channel.send(msg)
    
    #Run a round in the match
    async def run_match_contest(self):
        #Setup the contest options that the participants have access to
        views:list[ContestOptions] = []

        #Iterate between the two participants
        for parti in [self.participants[0]]:
           view = await create_contest(parti, f"{parti.mention}, you are engaged in a contest in {self.channel.jump_url}.\n How do you respond?")
           views.append(view)

        #Schedule to wait until both people have replied
        tasks = []
        for view in views:
            interaction_wait_task = asyncio.create_task(view.wait())
            tasks.append(interaction_wait_task)

        done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        
        #Determine and return the outcome
        outcome = compare_strikes(views[0].strike_type, StrikeType.FORCEFUL)
        return outcome
        

# Runs a match between two users
@bot.hybrid_command(name="run_match", description="Runs a match between two people.")
async def run_match (ctx: commands.Context, participant1:User, participant2:User) -> None:
    combat_match = CombatMatch(participant1, participant2, ctx.channel)
    await ctx.send("Starting match...")
    await combat_match.run_match()


##### Tournament and round commands and classes

class TournamentParticipant:
    def __init__(self, participant:User):
        self.participant = participant
        self.former_challengers:set[TournamentParticipant] = set()
        self.points = 0
        self.had_bye = False

class Tournament:
    def __init__(self, participants:list[User]):
        self.tournament_participants:list[TournamentParticipant] = []
        for participant in participants:
            self.tournament_participants.append(TournamentParticipant(participant))
        self.rounds:list[set[tuple[TournamentParticipant, TournamentParticipant]]] = []

    def standings(self) -> list[TournamentParticipant]:
        return sorted(self.tournament_participants, key=lambda p: -p.points)

    def create_pairings(self):
        G = nx.Graph()

        G.add_nodes_from(self.tournament_participants)

        for i in range (len(self.tournament_participants)):
            for j in range (i+1, len(self.tournament_participants)):
                if not self.tournament_participants[j] in self.tournament_participants[i].former_challengers:
                    #Calculate weighting based on minimising point difference
                    weighting = abs(self.tournament_participants[j].points - self.tournament_participants[i].points)

                    #Weight people who have not had byes higher to discourage multiple byes
                    if (not self.tournament_participants[j].had_bye) and (not self.tournament_participants[i].had_bye):
                        weighting += 20 #Should un-hardcode this number
                    G.add_edge(self.tournament_participants[j], self.tournament_participants[i], weight=weighting)

        #Produce set of matches from graph, and add it to the rounds
        best_matches:set[tuple[TournamentParticipant, TournamentParticipant]] = nx.algorithms.matching.min_weight_matching(G, weight="weight")
        self.rounds.append(best_matches)
        name_matches = []

        # plt.figure(figsize=(8, 6))
        # pos = nx.spring_layout(G, seed=42)  # seed for consistent layout
        # edge_labels = nx.get_edge_attributes(G, 'weight')

        # nx.draw_networkx_nodes(G, pos, node_size=1000, node_color='lightblue')
        # nx.draw_networkx_labels(G, pos, font_size=10, font_weight='bold', labels={n: n.participant.display_name for n in G})
        # nx.draw_networkx_edges(G, pos, width=2, alpha=0.5)
        # nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8)

        # plt.title("Swiss Pairing Graph (Spring Layout)")
        # plt.axis('off')
        # plt.tight_layout()
        # plt.show(block=False)
        # plt.pause(0.5)
        
        #Update prior competitors for each person, and calculate active and inactive competitors this round
        active_competitors:set[TournamentParticipant] = set()
        for (p1, p2) in best_matches:
            name_matches.append((p1.participant.display_name, p2.participant.display_name))
            p1.former_challengers.add(p2)
            p2.former_challengers.add(p1)

            active_competitors.add(p1)
            active_competitors.add(p2)

        inactive_competitors = set(self.tournament_participants) - active_competitors
        for inactive in inactive_competitors:
            inactive.had_bye = True

        message = "# Current Matches \n"
        for i, pairing in enumerate(best_matches):
            message += f"## Match {i+1} \n"
            message += f"{pairing[0].participant.display_name} ({pairing[0].points}) vs {pairing[1].participant.display_name} ({pairing[1].points}) \n"

        message += "# People with Byes \n"
        for inactive in inactive_competitors:
            message += inactive.participant.display_name + " (" + str(inactive.points) + ") \n"

        print(name_matches)
        return message

@bot.hybrid_command(name="test_tournament", description="Test")
async def test_tournament (ctx: commands.Context, player1:User, player2:User, player3:User, player4:User, player5:User) -> None:
    global tourn
    tourn = Tournament([player1, player2, player3, player4, player5])
    for j in range(3):
        msg = tourn.create_pairings()
        await ctx.send(msg)
        for (p1, p2) in tourn.rounds[j]:
            p1.points += randint(0,3)
            p2.points += randint(0,3)
    
    results = tourn.standings()
    final_result_msg = "# Final Standings \n"
    for result in results:
        final_result_msg += f"{result.participant.display_name}: {result.points} points \n"
    await ctx.send(final_result_msg)


##### Private channel commands

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


##### General functions to handle the running of the bot

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
