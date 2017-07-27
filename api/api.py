from flask import Flask
from flask import jsonify
from bson import json_util
import json
from pymongo import MongoClient
from flask import request
import os
from .db import db, redis_db
from rq import Queue
from .blockchain import storeBlockInDB
from .util import ANS_ID, ANC_ID, calculate_bonus

application = Flask(__name__)

q = Queue(connection=redis_db)

transaction_db = db['transactions']
blockchain_db = db['blockchain']
meta_db = db['meta']

symbol_dict = {ANS_ID: "NEO", ANC_ID: "GAS"}

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
    for tx_info in tx['vin_verbose']:
        if tx_info['address'] == address:
            if tx_info['asset'] == ANS_ID:
                neo_out += int(tx_info['value'])
            if tx_info['asset'] == ANC_ID:
                gas_out += float(tx_info['value'])
    for tx_info in tx['vout']:
        if tx_info['address'] == address:
            if tx_info['asset'] == ANS_ID:
                neo_in += int(tx_info['value'])
            if tx_info['asset'] == ANC_ID:
                gas_in += float(tx_info['value'])
    return {"txid": tx['txid'], "block_index":tx["block_index"], "NEO": neo_in - neo_out, "GAS": gas_in - gas_out}

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
@application.route("/nodes")
def nodes():
    nodes = meta_db.find_one({"name": "node_status"})["nodes"]
    return jsonify(nodes)

def compute_sys_fee(block_index):
    fees = [float(x["sys_fee"]) for x in transaction_db.find({ "$and":[
            {"sys_fee": {"$gt": 0}},
            {"block_index": {"$lt": block_index}}]})]
    return int(sum(fees))

# return node status
@application.route("/sys_fee/<block_index>")
def sysfee(block_index):
    sys_fee = compute_sys_fee(int(block_index))
    return jsonify({"fee": sys_fee})

# return changes in balance over time
@application.route("/balance_history/<address>")
def balance_history(address):
    transactions = transaction_db.find({"type":"ContractTransaction", "$or":[
        {"vout":{"$elemMatch":{"address":address}}},
        {"vin_verbose":{"$elemMatch":{"address":address}}}
    ]}).sort("block_index", -1)
    transactions = db2json({ "name":"transaction_history",
                             "address":address,
                             "history": [balance_for_transaction(address, x) for x in transactions]})
    return jsonify(transactions)

# get current block height
@application.route("/block_height")
def block_height():
    height = [x for x in blockchain_db.find().sort("index", -1).limit(1)][0]["index"]
    return jsonify({"block_height": height})

# get transaction data from the DB
@application.route("/get_transaction/<txid>")
def get_transaction(txid):
    return jsonify(db2json(transaction_db.find_one({"txid": txid})))

def collect_txids(txs):
    store = {"NEO": {}, "GAS": {}}
    for tx in txs:
        for k in ["NEO", "GAS"]:
            for tx_ in tx[k]:
                store[k][(tx_["txid"], tx_["index"])] = tx_
    return store

# get balance and unspent assets
@application.route("/balance/<address>")
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
    return jsonify({
        "NEO": {"balance": totals["NEO"],
                "unspent": [v for k,v in unspent["NEO"].items()]},
        "GAS": { "balance": totals["GAS"],
                 "unspent": [v for k,v in unspent["GAS"].items()] }})

# get available claims at an address
@application.route("/get_claim/<address>")
def get_claim(address):
    transactions = {t['txid']:t for t in transaction_db.find({"$or":[
        {"vout":{"$elemMatch":{"address":address}}},
        {"vin_verbose":{"$elemMatch":{"address":address}}}
    ]})}
    info_sent = [info_sent_transaction(address, t) for t in transactions.values()]
    sent_neo = collect_txids(info_sent)["NEO"]
    past_claims = get_past_claims(address)
    claimed_neo = get_claimed_txids(past_claims)
    valid_claims = [v for k,v in sent_neo.items() if not k in claimed_neo]
    block_diffs = []
    for tx in valid_claims:
        obj = {"txid": tx["txid"]}
        obj["start"] = transactions[tx['txid']]["block_index"]
        obj["value"] = tx["value"]
        obj["index"] = tx["index"]
        obj["end"] = transactions[tx['sending_id']]["block_index"]
        obj["sysfee"] = compute_sys_fee(obj["end"]) - compute_sys_fee(obj["start"])
        obj["claim"] = calculate_bonus([obj])
        block_diffs.append(obj)
    total = sum([x["claim"] for x in block_diffs])
    return jsonify({"total_claim": calculate_bonus(block_diffs), "claims": block_diffs, "past_claims": [k[0] for k,v in claimed_neo.items()]})

if __name__ == "__main__":
    application.run(host='0.0.0.0')
