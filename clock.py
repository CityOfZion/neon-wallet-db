from apscheduler.schedulers.blocking import BlockingScheduler
from rq import Queue
from api import redis_db as conn
from api.blockchain import storeLatestBlockInDB, getBlockCount, blockchain_db, storeBlockInDB, checkSeeds

q = Queue(connection=conn)

sched = BlockingScheduler()

# check for the latest block every 5 seconds
@sched.scheduled_job('interval', seconds=5)
def pollNode():
    q.enqueue(storeLatestBlockInDB)

# check for the latest block every 5 seconds
@sched.scheduled_job('interval', seconds=30)
def pollNode():
    q.enqueue(checkSeeds)

# intermittantly check for any blocks we missed by polling
@sched.scheduled_job('interval', minutes=1)
def syncBlockchain():
    currBlock = getBlockCount()["result"]
    lastTrustedBlock = blockchain_db["meta"].find_one({"name":"lastTrustedBlock"})["value"]
    laterBlocks = set([block["index"] for block in blockchain_db["blockchain"].find({"index": {"$gt": lastTrustedBlock}})])
    hash_set = {x:x for x in laterBlocks}
    newLastTrusted = lastTrustedBlock
    stopTrust = False
    for i in range(lastTrustedBlock+1, currBlock):
        if not i in hash_set:
            q.enqueue(storeBlockInDB, i)
            stopTrust = True
        if not stopTrust:
            newLastTrusted = i
    blockchain_db['meta'].update_one({"name":"lastTrustedBlock"}, {"$set": {"value": newLastTrusted}}, upsert=True)

sched.start()
