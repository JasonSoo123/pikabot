"""
Player-vs-Bot challenge script for PikaBot.

Connects to a local Pokémon Showdown server and challenges a specific username.
Usage:
    1. Start a local Showdown server: `pokemon-showdown` (or run the node server)
    2. In a browser, log in as "testing12344444" on the local server
    3. Run this script: `python -m pikabot.pvp`
"""
import asyncio
from poke_env.ps_client.server_configuration import LocalhostServerConfiguration
from poke_env.ps_client.account_configuration import AccountConfiguration

from pikabot.bot import PikaBot
from pikabot.team import EX_VGC_TEAM


async def main():
    """Challenge a specific user on the local Showdown server."""
    bot = PikaBot(
        battle_format="gen9championsvgc2026regmc",
        team=EX_VGC_TEAM,
        server_configuration=LocalhostServerConfiguration,
        account_configuration=AccountConfiguration("PikaBot", None),
    )

    print("Connecting to local Showdown server...")
    print("Challenging: testing12344444")

    await asyncio.wait_for(
        bot.send_challenges("testing12344444", n_challenges=1),
        timeout=120.0
        )


if __name__ == "__main__":
    asyncio.run(main())