import requests
import json
import sys
import os
from rq import Queue
from .db import db as blockchain_db
from .util import SEED_LIST, MAINNET_PORT, TESTNET_PORT

nodeAPI = os.environ.get('NODEAPI')
appName = os.environ.get('APPNAME')
net = os.environ.get('NET')

# helper for making node RPC request
def rpcRequest(method, params, nodeAPI=nodeAPI):
    return requests.post(nodeAPI, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 0}).json()

# get a block with the specified index from the node
# second param of 1 indicates verbose, which returns destructured hash
def getBlock(index):
    return rpcRequest("getblock", [index,1])

# get the current block height from the node
def getBlockCount(nodeAPI=nodeAPI):
    return rpcRequest("getblockcount", [], nodeAPI)

def checkSeeds():
    port = MAINNET_PORT if net == "MainNet" else TESTNET_PORT
    seeds = []
    for seed in SEED_LIST:
        test_rpc = seed + ":" + str(port)
        try:
            data = getBlockCount(test_rpc)
            seeds.append({"url": test_rpc, "status": True, "block_height": int(data["result"])})
        except:
            seeds.append({"url": test_rpc, "status": False, "block_height": None})
    blockchain_db['meta'].update_one({"name": "node_status"}, {"$set": {"nodes": seeds}}, upsert=True)

# get the latest block count and store last block in the database
def storeBlockInDB(block_index):
    data = getBlock(block_index)
    block_data = data["result"]
    # do transaction processing first, so that if anything goes wrong we don't update the chain data
    # the chain data is used for the itermittant syncing/correction step
    storeBlockTransactions(block_data)
    blockchain_db['blockchain'].update_one({"index": block_data["index"]}, {"$set": block_data}, upsert=True)

# store all the transactions in a block in the database
# if the transactions already exist, they will be updated
# if they don't exist, they will be replaced
def storeBlockTransactions(block):
    transactions = block['tx']
    out = []
    for t in transactions:
        t['block_index'] = block["index"]
        if t['type'] == 'ContractTransaction':
            input_transaction_data = []
            for vin in t['vin']:
                input_transaction_data.append(blockchain_db['transactions'].find_one({"txid": vin['txid']})['vout'][vin['vout']])
                input_transaction_data[-1]['txid'] = vin['txid']
            t['vin_verbose'] = input_transaction_data
        blockchain_db['transactions'].update_one({"txid": t["txid"]}, {"$set": t}, upsert=True)

def storeLatestBlockInDB():
    currBlock = getBlockCount()["result"]
    # height - 1 = current block
    storeBlockInDB(currBlock-1)

checkSeeds()
