from flask import Flask
from flask import jsonify
from bson import json_util
import json
from pymongo import MongoClient
from flask import request
from flask.ext.cache import Cache
from flask_cors import CORS, cross_origin
import os
from .db import db, redis_db
from rq import Queue
from .blockchain import storeBlockInDB, get_highest_node
from .util import ANS_ID, ANC_ID, calculate_bonus
import random
from werkzeug.contrib.cache import MemcachedCache
import time

application = Flask(__name__)
CORS(application)

NET = os.environ.get('NET')

q = Queue(connection=redis_db)

transaction_db = db['transactions']
blockchain_db = db['blockchain']
meta_db = db['meta']
logs_db = db['logs']
address_db = db['addresses']

symbol_dict = {ANS_ID: "NEO", ANC_ID: "GAS"}

# Constants
USE_MEMCACHE = True

## Cache
cache_config = {}
cache_config['CACHE_TYPE'] = 'simple'

### Memcache

if USE_MEMCACHE:
    username = os.environ.get('MEMCACHIER_USERNAME') or os.environ.get('MEMCACHE_USERNAME')
    password = os.environ.get('MEMCACHIER_PASSWORD') or os.environ.get('MEMCACHE_PASSWORD')
    servers = os.environ.get('MEMCACHIER_SERVERS') or os.environ.get('MEMCACHE_SERVERS')
    if username and password and servers:
        servers = servers.split(';')
        cache_config['CACHE_TYPE'] = 'flask_cache_backends.bmemcached'
        cache_config['CACHE_MEMCACHED_USERNAME'] = username
        cache_config['CACHE_MEMCACHED_PASSWORD'] = password
        cache_config['CACHE_MEMCACHED_SERVERS'] = servers
cache = Cache(application, config=cache_config)

def db2json(db_obj):
    return json.loads(json.dumps(db_obj, indent=4, default=json_util.default))

# return a dictionary of spent (txids, vout) => transaction when spent
# TODO: add vout to this
def get_vin_txids(txs):
    spent_ids = {"NEO":{}, "GAS":{}}
    for tx in txs:
        for tx_sent in tx["vin_verbose"]:
            asset_symbol = symbol_dict[tx_sent["asset"]]
            spent_ids[asset_symbol][(tx_sent["txid"], tx_sent["n"])] = tx
    return spent_ids

# return a dictionary of claimed (txids, vout) => transaction when claimed
def get_claimed_txids(txs):
    claimed_ids = {}
    for tx in txs:
        for tx_claimed in tx["claims"]:
            claimed_ids[(tx_claimed["txid"], tx_claimed['vout'])] = tx
    return claimed_ids

def balance_for_transaction(address, tx):
    neo_out, neo_in = 0, 0
    gas_out, gas_in = 0.0, 0.0
    neo_sent, gas_sent = False, False
    if "vin_verbose" in tx:
        for tx_info in tx['vin_verbose']:
            if tx_info['address'] == address:
                if tx_info['asset'] == ANS_ID:
                    neo_out += int(tx_info['value'])
                    neo_sent = True
                if tx_info['asset'] == ANC_ID:
                    gas_out += float(tx_info['value'])
                    gas_sent = True
    if "vout" in tx:
        for tx_info in tx['vout']:
            if tx_info['address'] == address:
                if tx_info['asset'] == ANS_ID:
                    neo_in += int(tx_info['value'])
                    neo_sent = True
                if tx_info['asset'] == ANC_ID:
                    gas_in += float(tx_info['value'])
                    gas_sent = True
    return {"txid": tx['txid'], "block_index":tx["block_index"],
        "NEO": neo_in - neo_out,
        "GAS": gas_in - gas_out,
        "neo_sent": neo_sent,
        "gas_sent": gas_sent}

# walk over "vout" transactions to collect those that match desired address
def info_received_transaction(address, tx):
    out = {"NEO":[], "GAS":[]}
    neo_tx, gas_tx = [], []
    if not "vout" in tx:
        return out
    for i,obj in enumerate(tx["vout"]):
        if obj["address"] == address:
            if obj["asset"] == ANS_ID:
                neo_tx.append({"value": int(obj["value"]), "index": obj["n"], "txid": tx["txid"]})
            if obj["asset"] == ANC_ID:
                gas_tx.append({"value": float(obj["value"]), "index": obj["n"], "txid": tx["txid"]})
    out["NEO"] = neo_tx
    out["GAS"] = gas_tx
    return out

def info_sent_transaction(address, tx):
    out = {"NEO":[], "GAS":[]}
    neo_tx, gas_tx = [], []
    if not "vin_verbose" in tx:
        return out
    for i,obj in enumerate(tx["vin_verbose"]):
        if obj["address"] == address:
            if obj["asset"] == ANS_ID:
                neo_tx.append({"value": int(obj["value"]), "index": obj["n"], "txid": obj["txid"], "sending_id":tx["txid"]})
            if obj["asset"] == ANC_ID:
                gas_tx.append({"value": float(obj["value"]), "index": obj["n"], "txid": obj["txid"], "sending_id":tx["txid"]})
    out["NEO"] = neo_tx
    out["GAS"] = gas_tx
    return out

# get the amount sent to an address from the vout list
def amount_sent(address, asset_id, vout):
    total = 0
    for obj in vout:
        if obj["address"] == address and asset_id == obj["asset"]:
            if asset_id == ANS_ID:
                total += int(obj["value"])
            else:
                total += float(obj["value"])
    return total

def get_past_claims(address):
    return [t for t in transaction_db.find({
        "$and":[
        {"type":"ClaimTransaction"},
        {"vout":{"$elemMatch":{"address":address}}}]})]

def is_valid_claim(tx, address, spent_ids, claim_ids):
    return tx['txid'] in spent_ids and not tx['txid'] in claim_ids and len(info_received_transaction(address, tx)["NEO"]) > 0

# return node status
@application.route("/v1/network/nodes")
def nodes():
    nodes = meta_db.find_one({"name": "node_status"})["nodes"]
    return jsonify({"net": NET, "nodes": nodes})

# return node status
@application.route("/v1/network/best_node")
def highest_node():
    nodes = meta_db.find_one({"name": "node_status"})["nodes"]
    highest_node = get_highest_node()
    return jsonify({"net": NET, "node": highest_node})

# def compute_sys_fee(block_index):
#     block_key = "sys_fee_{}".format(block_index)
#     if cache.get(block_key):
#         return cache.get(block_key)
#     else:
#         fees = [float(x["sys_fee"]) for x in transaction_db.find({ "$and":[
#                 {"sys_fee": {"$gt": 0}},
#                 {"block_index": {"$lte": block_index}}]})]
#         total = int(sum(fees))
#         cache.set(block_key, total, timeout=10000)
#         return total

def compute_sys_fee(block_index):
    block_key = "sys_fee_{}".format(block_index)
    if cache.get(block_key):
        print("using cache")
        return cache.get(block_key)
    print(block_index)
    print("slowest")
    fees = [float(x["sys_fee"]) for x in transaction_db.find({ "$and":[
                    {"sys_fee": {"$gt": 0}},
                    {"block_index": {"$lte": block_index}}]})]
    total = int(sum(fees))
    cache.set(block_key, total, timeout=10000)
    return total

def compute_sys_fee_diff(index1, index2):
#     return compute_sys_fee(index2) - compute_sys_fee(index1)
    fees = [float(x["sys_fee"]) for x in transaction_db.find({ "$and":[
                {"sys_fee": {"$gt": 0}},
                {"block_index": {"$gte": index1}},
                {"block_index": {"$lte": index2}} ]})]
    total = int(sum(fees))
    return total

# def compute_sys_fee_diff(index1, index2):
#     print(index1, index2)
#     index1 = int(blockchain_db.find_one({"index": index1})["sys_fee"])
#     index2 = int(blockchain_db.find_one({"index": index2})["sys_fee"])
#     print(index1, index2)
#     return index2 - index1

def compute_net_fee(block_index):
    fees = [float(x["net_fee"]) for x in transaction_db.find({ "$and":[
            {"net_fee": {"$gt": 0}},
            {"block_index": {"$lt": block_index}}]})]
    return int(sum(fees))

# return node status
@application.route("/v1/block/sys_fee/<block_index>")
@cache.cached(timeout=500)
def sysfee(block_index):
    sys_fee = compute_sys_fee(int(block_index))
    return jsonify({"net": NET, "fee": sys_fee})

# return changes in balance over time
@application.route("/v1/address/history/<address>")
@cache.cached(timeout=15)
def balance_history(address):
    transactions = transaction_db.find({"$or":[
        {"vout":{"$elemMatch":{"address":address}}},
        {"vin_verbose":{"$elemMatch":{"address":address}}}
    ]}).sort("block_index", -1).limit(25)
    transactions = db2json({ "net": NET,
                             "name":"transaction_history",
                             "address":address,
                             "history": [balance_for_transaction(address, x) for x in transactions]})
    return jsonify(transactions)

def get_db_height():
    return [x for x in blockchain_db.find().sort("index", -1).limit(1)][0]["index"]

# get current block height
@application.route("/v1/block/height")
def block_height():
    height = get_db_height()
    return jsonify({"net": NET, "block_height": height})

# get transaction data from the DB
@application.route("/v1/transaction/<txid>")
@cache.cached(timeout=500)
def get_transaction(txid):
    return jsonify({**db2json(transaction_db.find_one({"txid": txid})), "net": NET} )

def collect_txids(txs):
    store = {"NEO": {}, "GAS": {}}
    for tx in txs:
        for k in ["NEO", "GAS"]:
            for tx_ in tx[k]:
                store[k][(tx_["txid"], tx_["index"])] = tx_
    return store

def filter_gas(gas_txs, max_gas, address):
    if address in ["ALxkLkCY1iij3yoZ6XxEHLVQ6ihixJJNcB", "AcQ6FCjJ8EqyKwFUeZ4Ac2pnTg4oHr8UBt"]:
        return gas_txs
    out = {}
    total = 0.0
    for k,v in gas_txs.items():
        if total + v["value"] > max_gas:
            continue
        else:
            total += v["value"]
            out[k] = v
    return out

# get balance and unspent assets
@application.route("/v1/address/balance/<address>")
@cache.cached(timeout=15)
def get_balance(address):
    transactions = [t for t in transaction_db.find({"$or":[
        {"vout":{"$elemMatch":{"address":address}}},
        {"vin_verbose":{"$elemMatch":{"address":address}}}
    ]})]
    info_sent = [info_sent_transaction(address, t) for t in transactions]
    info_received = [info_received_transaction(address, t) for t in transactions]
    sent = collect_txids(info_sent)
    received = collect_txids(info_received)
    unspent = {k:{k_:v_ for k_,v_ in received[k].items() if (not k_ in sent[k])} for k in ["NEO", "GAS"]}
    totals = {k:sum([v_["value"] for k_,v_ in unspent[k].items()]) for k in ["NEO", "GAS"]}
    if random.randint(1,10) == 1:
        logs_db.update_one({"address": address}, {"$set": {
            "address": address,
            "NEO": totals["NEO"],
            "GAS": totals["GAS"]
        }}, upsert=True)
    return jsonify({
        "net": NET,
        "address": address,
        "NEO": {"balance": totals["NEO"],
                "unspent": [v for k,v in unspent["NEO"].items()]},
        "GAS": { "balance": totals["GAS"],
                # "unspent": [v for k,v in unspent["GAS"].items()] }})
                 "unspent": [v for k,v in filter_gas(unspent["GAS"], 5000, address).items()] }})

def filter_claimed_for_other_address(claims):
    out_claims = []
    for claim in claims.keys():
        if not transaction_db.find_one({"type":"ClaimTransaction", "$and": [{"claims": {"$elemMatch": {"txid": claim[0]}}}, {"claims": {"$elemMatch": {"vout": claim[1]}}}]}):
            out_claims.append(claims[claim])
    return out_claims

def compute_claims(claims, transactions, end_block=False):
    block_diffs = []
    for tx in claims:
        obj = {"txid": tx["txid"]}
        obj["start"] = transactions[tx['txid']]["block_index"]
        obj["value"] = tx["value"]
        obj["index"] = tx["index"]
        if not end_block:
            obj["end"] = transactions[tx['sending_id']]["block_index"]
        else:
            obj["end"] = end_block
        obj["sysfee"] = compute_sys_fee_diff(obj["start"], obj["end"])
        obj["claim"] = calculate_bonus([obj])
        block_diffs.append(obj)
    return block_diffs

def get_address_txs(address):
    query = address_db.find_one({"address": address})
    if query:
        return query["txs"]
    else:
        transactions = {t['txid']:t for t in transaction_db.find({"$or":[
            {"vout":{"$elemMatch":{"address":address}}},
            {"vin_verbose":{"$elemMatch":{"address":address}}}
        ]})}
        address_db.update_one({"address": address}, {"$set": {"txs": transactions}}, upsert=True)
        return transactions

# get available claims at an address
@application.route("/v1/address/claims/<address>")
# @cache.cached(timeout=15)
def get_claim(address):
    # try:
    #     start = time.time()
    #     transactions = {t['txid']:t for t in transaction_db.find({"$or":[
    #         {"vout":{"$elemMatch":{"address":address}}},
    #         {"vin_verbose":{"$elemMatch":{"address":address}}}
    #     ]})}
    #     print("to get transactions {}".format(time.time() - start))
    #     # get sent neo info
    #     info_sent = [info_sent_transaction(address, t) for t in transactions.values()]
    #     sent_neo = collect_txids(info_sent)["NEO"]
    #     # get received neo info
    #     info_received = [info_received_transaction(address, t) for t in transactions.values()]
    #     received_neo = collect_txids(info_received)["NEO"]
    #     unspent_neo = {k:v for k,v in received_neo.items() if not k in sent_neo}
    #     # get claim info
    #     past_claims = get_past_claims(address)
    #     claimed_neo = get_claimed_txids(past_claims)
    #     valid_claims = {k:v for k,v in sent_neo.items() if not k in claimed_neo}
    #     valid_claims = filter_claimed_for_other_address(valid_claims)
    #     block_diffs = compute_claims(valid_claims, transactions)
    #     total = sum([x["claim"] for x in block_diffs])
    #     # now do for unspent
    #     height = get_db_height()
    #     start = time.time()
    #     unspent_diffs = compute_claims([v for k,v in unspent_neo.items()], transactions, height)
    #     print("to compute claims: {}".format(time.time() - start))
    #     print(unspent_diffs)
    #     unspent_claim_total = sum([x["claim"] for x in block_diffs])
    #     print(unspent_claim_total)
    #     return jsonify({
    #         "net": NET,
    #         "address": address,
    #         "total_claim": calculate_bonus(block_diffs),
    #         "total_unspent_claim": calculate_bonus(unspent_diffs),
    #         "claims": block_diffs})
    # except:
    #     print("something went wwrong!!")
    return jsonify({
        "net": NET,
        "address": address,
        "total_claim": 0,
        "total_unspent_claim": 0,
        "claims": [] })


if __name__ == "__main__":
    application.run(host='0.0.0.0')
