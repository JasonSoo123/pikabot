from poke_env.battle.status import Status
from poke_env.battle.target import Target

PROTECT_MOVES = ["protect", "detect", "banefulbunker", "burningbulwark", "craftyshield", 
                 "kingsshield", "maxguard", "obtruct", "spikyshield", "silktrap"]

NON_SINGLE_TARGET = {Target.ALL_ADJACENT_FOES, Target.ALL_ADJACENT, Target.ALL, Target.FOE_SIDE}

STATUS_MOVES = [Status.BRN, Status.TOX, Status.PSN, Status.FRZ, Status.PAR, Status.SLP]

SELF_OR_ALLY_TARGETS = [
    Target.SELF,
    Target.ALLY_SIDE,
    Target.ALLY_TEAM,
    Target.ADJACENT_ALLY,
    Target.ADJACENT_ALLY_OR_SELF,
    Target.ALLIES,
    Target.ALL
]

POWDER_MOVES = {"spore", "sleeppowder", "ragepowder", "stunspore", "poisonpowder"}

SETUP_MOVES = {
    "swordsdance": ["atk"],
    "nastyplot": ["spa"],
    "dragondance": ["atk", "spe"],
    "calmmind": ["spa", "spd"],
    "quiverdance": ["spa", "spd", "spe"],
    "bulkup": ["atk", "def"],
    "irondefense": ["def"],
    "coils": ["atk", "def", "accuracy"],
    "agility": ["spe"]
}
