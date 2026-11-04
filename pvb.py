"""
Player-vs-Bot challenge script for PikaBot.

Connects to a local Pokémon Showdown server and challenges a specific username.
Usage:
    1. Start a local Showdown server: `pokemon-showdown` (or run the node server)
    2. In a browser, log in as "testing12344444" on the local server
    3. Run this script: `python -m pikabot.pvb`
"""
import asyncio
import random
from poke_env.ps_client.server_configuration import LocalhostServerConfiguration
from poke_env.ps_client.account_configuration import AccountConfiguration

from pikabot.bot import PikaBot
from pikabot.team import VGC_TEAMS_LIST


async def main():
    """Challenge a specific user on the local Showdown server with a random VGC team."""
    team = random.choice(VGC_TEAMS_LIST)
    bot = PikaBot(
        battle_format="gen9championsvgc2026regmc",
        team=team,
        server_configuration=LocalhostServerConfiguration,
        account_configuration=AccountConfiguration("PikaBot", None),
    )

    print("connecting to local showdown server...")
    print("challenging: testing12344444")

    await asyncio.wait_for(
        bot.send_challenges("testing12344444", n_challenges=1),
        timeout=120.0
        )


if __name__ == "__main__":
    asyncio.run(main())