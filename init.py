from api import blockchain_db

# set data to keep track of last fully synced block
blockchain_db["meta"].insert_one({"name":"lastTrustedBlock", "value":1162327})
