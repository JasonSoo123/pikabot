import asyncio

from poke_env.ps_client.server_configuration import LocalhostServerConfiguration
from pikabot.bot import PikaBot
from pikabot.team import VGC_TEAMS_LIST


async def run_team_vs_team(team1_str: str, team2_str: str, n_battles: int = 5):
    """Run battles between two teams."""
    player1 = PikaBot(
        battle_format="gen9championsvgc2026regmc",
        team=team1_str,
    )

    player2 = PikaBot(
        battle_format="gen9championsvgc2026regmc",
        team=team2_str,
    )

    # Run direct battles (no server needed)
    await player1.battle_against(player2, n_battles=n_battles)


async def main():
    total_teams = len(VGC_TEAMS_LIST)
    battles_per_pair = 5
    total_battles = total_teams * total_teams * battles_per_pair

    print(f"Starting tournament: {total_teams} teams x {total_teams} teams x {battles_per_pair} battles = {total_battles} total battles")

    battle_count = 0
    for i, team1 in enumerate(VGC_TEAMS_LIST):
        for j, team2 in enumerate(VGC_TEAMS_LIST):
            
            if i < 4 or (i == 4 and j < 33):
                battle_count += battles_per_pair
                continue
            
            print(f"Matchup {i*total_teams + j + 1}/{total_teams*total_teams}: Team {i+1} vs Team {j+1}")
            await run_team_vs_team(team1, team2, n_battles=battles_per_pair)
            battle_count += battles_per_pair
            print(f"  Completed {battle_count}/{total_battles} battles")

    print(f"Complete! Total battles: {battle_count}")


if __name__ == "__main__":
    asyncio.run(main())