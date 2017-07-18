import requests
import json
import sys
import os
from rq import Queue
from worker import conn

nodeAPI = os.environ.get('NODEAPI')
appName = os.environ.get('APPNAME')


def rpcRequest(method, params):
    return requests.post(nodeAPI, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 0}).json()

def getBlock(index):
    return rpcRequest("getblock", [index,1])

def getBlockCount():
    return rpcRequest("getblockcount", [])

def sync_blockchain():
    currBlock = getBlockCount()
    requests.post(appName+"/sync_block", json={"block":currBlock["result"]})
