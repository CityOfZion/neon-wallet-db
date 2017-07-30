ANS_ID = "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b"
ANC_ID = "602c79718b16e442de58778e148d0b1084e3b2dffd5de6b7b16cee7969282de7"

NEO_SEED_LIST = ["http://seed{}.neo.org".format(x) for x in [1,2,3,4,5]] + ["http://seed8.antshares.org"]
MAINNET_PORT = 10332
NEO_MAINNET = [node + ":" + str(MAINNET_PORT) for node in NEO_SEED_LIST]
TESTNET_PORT = 20332
NEO_TESTNET = [node + ":" + str(TESTNET_PORT) for node in NEO_SEED_LIST]
OTCGO_SEED_LIST = ["http://api.otcgo.cn"]
OTCGO_MAINNET = [node + ":" + str(MAINNET_PORT) for node in OTCGO_SEED_LIST]
OTCGO_TESTNET = [node + ":" + str(TESTNET_PORT) for node in OTCGO_SEED_LIST]

COZ_MAINNET = ["http://seed{}.cityofzion.io:8080".format(i) for i in [1,2,3,4,5]]
COZ_TESTNET = ["http://test{}.cityofzion.io:8880".format(i) for i in [1,2,3,4,5]]

MAINNET_SEEDS = NEO_MAINNET + OTCGO_MAINNET + COZ_MAINNET
TESTNET_SEEDS = NEO_TESTNET + OTCGO_TESTNET + COZ_TESTNET


GENERATION_AMOUNT = [8, 7, 6, 5, 4, 3, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
GENERATION_LENGTH = 22
DECREMENT_INTERVAL = 2000000

# implementation ported directly from node core
def calculate_bonus(claims):
    amount_claimed = 0
    for claim in claims:
        start_height = int(claim["start"])
        end_height = int(claim["end"])
        amount = 0
        ustart = int(start_height / DECREMENT_INTERVAL)
        if ustart < GENERATION_LENGTH:
            istart = start_height % DECREMENT_INTERVAL
            uend = int(end_height / DECREMENT_INTERVAL)
            iend = end_height % DECREMENT_INTERVAL
            if uend >= GENERATION_LENGTH:
                uend = GENERATION_LENGTH
                iend = 0
            if iend == 0:
                uend = uend - 1
                iend = DECREMENT_INTERVAL
            while ustart < uend:
                amount += (DECREMENT_INTERVAL - istart) * GENERATION_AMOUNT[ustart]
                ustart += 1
                istart = 0
            amount += (iend - istart) * GENERATION_AMOUNT[ustart]
        amount += claim["sysfee"]
        amount_claimed += int(claim["value"]) * amount
    return amount_claimed
