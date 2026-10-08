import asyncio

from poke_env.player import RandomPlayer
from pikabot.bot import PikaBot
from pikabot.team import EX_VGC_TEAM

async def main():
    player1 = PikaBot(
        battle_format="gen9championsvgc2026regma",
        team=EX_VGC_TEAM
    )
    
    player2 = RandomPlayer(
        battle_format="gen9championsvgc2026regma",
        team=EX_VGC_TEAM
    )

    # Set n_battles=1 so you can see it complete a single match
    await player1.battle_against(player2, n_battles=1)

if __name__ == "__main__":
    asyncio.run(main())
