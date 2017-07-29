from apscheduler.schedulers.blocking import BlockingScheduler
from rq import Queue
from api import redis_db as conn
from api.blockchain import storeLatestBlockInDB, getBlockCount, blockchain_db, storeBlockInDB, checkSeeds, get_highest_node

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
@sched.scheduled_job('interval', seconds=10)
def syncBlockchain():
    nodeAPI = get_highest_node()
    currBlock = getBlockCount(nodeAPI)["result"]
    lastTrustedBlock = blockchain_db["meta"].find_one({"name":"lastTrustedBlock"})["value"]
    laterBlocks = set([block["index"] for block in blockchain_db["blockchain"].find({"index": {"$gt": lastTrustedBlock}})])
    hash_set = {x:x for x in laterBlocks}
    newLastTrusted = lastTrustedBlock
    print("missing", len(laterBlocks))
    stopTrust = False
    for i in range(lastTrustedBlock-1, currBlock):
        if not i in hash_set:
            print("repairing {}".format(i))
            q.enqueue(storeBlockInDB, i, nodeAPI)
            stopTrust = True
        if not stopTrust:
            newLastTrusted = i
    print("newLastTrusted", newLastTrusted)
    blockchain_db['meta'].update_one({"name":"lastTrustedBlock"}, {"$set": {"value": newLastTrusted}}, upsert=True)
    print("done")

sched.start()
