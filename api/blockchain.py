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
def getBlock(index, nodeAPI=nodeAPI):
    return rpcRequest("getblock", [index,1], nodeAPI)

# get the current block height from the node
def getBlockCount(nodeAPI=False):
    if nodeAPI == False:
        nodeAPI = get_highest_node()
    return rpcRequest("getblockcount", [], nodeAPI)

def checkSeeds():
    port = MAINNET_PORT if net == "MainNet" else TESTNET_PORT
    seeds = []
    for seed in SEED_LIST:
        test_rpc = seed + ":" + str(port)
        try:
            data = getBlockCount(test_rpc)
            getBlock(int(data["result"])-1, test_rpc)
            seeds.append({"url": test_rpc, "status": True, "block_height": int(data["result"])})
        except:
            seeds.append({"url": test_rpc, "status": False, "block_height": None})
    blockchain_db['meta'].update_one({"name": "node_status"}, {"$set": {"nodes": seeds}}, upsert=True)

# get the node with the highest block height
def get_highest_node():
    nodes_data = blockchain_db['meta'].find_one({"name":"node_status"})["nodes"]
    return sorted([x for x in nodes_data if x["block_height"] != None], key=lambda x: x["block_height"], reverse=True)[0]["url"]

# get the latest block count and store last block in the database
def storeBlockInDB(block_index, nodeAPI=False):
    if not nodeAPI:
        nodeAPI = get_highest_node()
    data = getBlock(block_index, nodeAPI=nodeAPI)
    block_data = data["result"]
    # do transaction processing first, so that if anything goes wrong we don't update the chain data
    # the chain data is used for the itermittant syncing/correction step
    if storeBlockTransactions(block_data):
        blockchain_db['blockchain'].update_one({"index": block_data["index"]}, {"$set": block_data}, upsert=True)

# store all the transactions in a block in the database
# if the transactions already exist, they will be updated
# if they don't exist, they will be replaced
def storeBlockTransactions(block):
    transactions = block['tx']
    out = []
    for t in transactions:
        t['block_index'] = block["index"]
        t['sys_fee'] = float(t['sys_fee'])
        t['net_fee'] = float(t['net_fee'])
        if t['type'] == 'ContractTransaction':
            input_transaction_data = []
            for vin in t['vin']:
                try:
                    input_transaction_data.append(blockchain_db['transactions'].find_one({"txid": vin['txid']})['vout'][vin['vout']])
                    input_transaction_data[-1]['txid'] = vin['txid']
                except:
                    print("failed on transaction lookup")
                    print(vin['txid'])
                    return False
            t['vin_verbose'] = input_transaction_data
        blockchain_db['transactions'].update_one({"txid": t["txid"]}, {"$set": t}, upsert=True)
    return True

def storeLatestBlockInDB():
    nodeAPI = get_highest_node()
    print("updating latest block with {}".format(nodeAPI))
    currBlock = getBlockCount(nodeAPI=nodeAPI)["result"]
    print("current block {}".format(currBlock))
    # height - 1 = current block
    storeBlockInDB(currBlock-1, nodeAPI)
