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

# return a dictionary of spent txids => transaction when spent
def get_vin_txids(txs):
    spent_ids = {"NEO":{}, "GAS":{}}
    for tx in txs:
        for tx_sent in tx["vin_verbose"]:
            asset_symbol = symbol_dict[tx_sent["asset"]]
            spent_ids[asset_symbol][tx_sent["txid"]] = tx
    return spent_ids

# return a dictionary of claimed txids => transaction when claimed
def get_claimed_txids(txs):
    claimed_ids = {}
    for tx in txs:
        for tx_claimed in tx["claims"]:
            claimed_ids[tx_claimed["txid"]] = tx
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
    out = {"txid": tx["txid"]}
    neo_tx, gas_tx = None, None
    index_neo, index_gas = None, None
    for i,obj in enumerate(tx["vout"]):
        if obj["address"] == address:
            if obj["asset"] == ANS_ID:
                neo_tx = int(obj["value"])
                index_neo = i
            if obj["asset"] == ANC_ID:
                gas_tx = float(obj["value"])
                index_gas = i
    if (not neo_tx) and (not gas_tx):
        raise Exception("Transaction contains no asset sent to this address")
    if neo_tx:
        out["NEO"] = {"value": neo_tx, "index": index_neo}
    if gas_tx:
        out["GAS"] = {"value": gas_tx, "index": index_gas}
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

# helper function to get all transactions from an address
def get_transactions(address):
    receiver = [t for t in transaction_db.find({
                        "vout":{"$elemMatch":{"address":address}}})]
    sender = [t for t in transaction_db.find({ #{"type":"ContractTransaction",
                        "vin_verbose":{"$elemMatch":{"address":address}}})]
    return receiver, sender

def get_past_claims(address):
    return [t for t in transaction_db.find({
        "type":"ClaimTransaction",
        "vout":{"$elemMatch":{"address":address}}})]

def is_valid_claim(tx, address, spent_ids, claim_ids):
    # if tx['block_index'] < 270000:
    #     return False
    # if tx["vin_verbose"][0]["address"] != address:
    #     return False
    return tx['txid'] in spent_ids and not tx['txid'] in claim_ids and "NEO" in info_received_transaction(address, tx)

# return node status
@application.route("/nodes")
def nodes():
    nodes = meta_db.find_one({"name": "node_status"})["nodes"]
    return jsonify(nodes)

# return node status
@application.route("/sys_fee/<block_index>")
def sysfee(block_index):
    fees = [float(x["sys_fee"]) for x in transaction_db.find({"$and":[{"sys_fee": {"$ne": "0"}}, {"block_index": {"$lt": int(block_index)}}]})]
    fee = sum(fees)
    return jsonify({"fee": int(fee)})

# return all transactions associated with an address (sending to or sent from)
@application.route("/transaction_history/<address>")
def transaction_history(address):
    receiver, sender = get_transactions(address)
    transactions = db2json({ "name":"transaction_history",
                             "address":address,
                             "receiver": receiver,
                             "sender": sender })
    return jsonify(transactions)

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

# get balance and unspent assets
@application.route("/balance/<address>")
def get_balance(address):
    receiver, sender = get_transactions(address)
    spent_ids = get_vin_txids(sender)
    spent_ids_gas = spent_ids["GAS"]
    spent_ids_neo = spent_ids["NEO"]
    unspent_neo = [x for x in receiver if 'NEO' in info_received_transaction(address, x) and not x['txid'] in spent_ids_neo]
    unspent_gas = [x for x in receiver if 'GAS' in info_received_transaction(address, x) and not x['txid'] in spent_ids_gas]
    neo_total = sum([amount_sent(address, ANS_ID, x["vout"]) for x in unspent_neo])
    gas_total = sum([amount_sent(address, ANC_ID, x["vout"]) for x in unspent_gas])
    return jsonify({
        "NEO": {"balance": neo_total,
                "unspent": [{**info_received_transaction(address, tx)["NEO"], "txid": tx['txid']} for tx in unspent_neo] },
        "GAS": { "balance": gas_total,
                 "unspent": [{**info_received_transaction(address, tx)["GAS"], "txid": tx['txid']} for tx in unspent_gas] }})

# get available claims at an address
@application.route("/get_claim/<address>")
def get_claim(address):
    receiver, sender = get_transactions(address)
    past_claims = get_past_claims(address)
    spent_ids = get_vin_txids(sender)
    spent_ids_neo = spent_ids["NEO"]
    claim_ids = get_claimed_txids(past_claims)
    valid_claims = [tx for tx in receiver if is_valid_claim(tx, address, spent_ids_neo, claim_ids)]
    block_diffs = []
    for tx in valid_claims:
        obj = {"txid": tx["txid"]}
        obj["start"] = tx["block_index"]
        info = info_received_transaction(address, tx)
        obj["value"] = info["NEO"]["value"]
        obj["index"] = info["NEO"]["index"]
        when_spent = spent_ids_neo[tx["txid"]]
        obj["end"] = when_spent["block_index"]
        obj["claim"] = calculate_bonus([obj])
        block_diffs.append(obj)
    total = sum([x["claim"] for x in block_diffs])
    return jsonify({"total_claim": calculate_bonus(block_diffs), "claims": block_diffs, "past_claims": [k for k,v in claim_ids.items()]})

if __name__ == "__main__":
    application.run(host='0.0.0.0')
