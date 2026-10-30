import asyncio

from poke_env.ps_client.server_configuration import LocalhostServerConfiguration
from pikabot.bot import PikaBot
from pikabot.team import EX_VGC_TEAM

async def main():
    player1 = PikaBot(
        battle_format="gen9championsvgc2026regmc",
        team=EX_VGC_TEAM
    )

    player2 = PikaBot(
        battle_format="gen9championsvgc2026regmc",
        team=EX_VGC_TEAM
    )

    # Run direct battles (no server needed)
    await player1.battle_against(player2, n_battles=1)

if __name__ == "__main__":
    asyncio.run(main())