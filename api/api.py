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
from .util import ANS_ID, ANC_ID

application = Flask(__name__)

q = Queue(connection=redis_db)

transaction_db = db['transactions']
blockchain_db = db['blockchain']

def db2json(db_obj):
    return json.loads(json.dumps(db_obj, indent=4, default=json_util.default))

# return a dictionary of spent txids => transaction when spent
def get_vin_txids(txs):
    spent_ids = {}
    for tx in txs:
        for tx_sent in tx["vin"]:
            spent_ids[tx_sent["txid"]] = tx
    return spent_ids

# return a dictionary of claimed txids => transaction when claimed
def get_claimed_txids(txs):
    claimed_ids = {}
    for tx in txs:
        for tx_claimed in tx["claims"]:
            claimed_ids[tx_claimed["txid"]] = tx
    return claimed_ids

# walk over "vout" transactions to collect those that match desired address
def info_received_transaction(address, tx):
    out = {"txid": tx["txid"]}
    neo_tx, gas_tx = None, None
    index = None
    for i,obj in enumerate(tx["vout"]):
        if obj["address"] == address:
            index = i
            if obj["asset"] == ANS_ID:
                neo_tx = int(obj["value"])
            elif obj["asset"] == ANC_ID:
                gas_tx = int(obj["value"])
            else:
                raise Exception("Not a valid asset")
    if neo_tx and gas_tx:
        raise Exception("Cannot receive two different assets in one transaction")
    elif (not neo_tx) and (not gas_tx):
        raise Exception("Transaction contains no asset sent to this address")
    elif neo_tx:
        out["asset"] = "NEO"
        out["value"] = neo_tx
    else:
        out["asset"] = "GAS"
        out["value"] = gas_tx
    out["index"] = index
    return out

# get the amount sent to an address from the vout list
def amount_sent(address, asset_id, vout):
    total = 0
    for obj in vout:
        if obj["address"] == address and asset_id == obj["asset"]:
            total += int(obj["value"])
    return total

# helper function to get all transactions from an address
def get_transactions(address):
    receiver = [t for t in transaction_db.find({"type":"ContractTransaction",
                        "vout":{"$elemMatch":{"address":address}}})]
    sender = [t for t in transaction_db.find({"type":"ContractTransaction",
                        "vin_verbose":{"$elemMatch":{"address":address}}})]
    return receiver, sender

def get_past_claims(address):
    return [t for t in transaction_db.find({
        "type":"ClaimTransaction",
        "vout":{"$elemMatch":{"address":address}}})]

def is_valid_claim(tx, address, spent_ids, claim_ids):
    return tx['txid'] in spent_ids and not tx['txid'] in claim_ids and info_received_transaction(address, tx)["asset"] == "NEO"

# return all transactions associated with an address (sending to or sent from)
@application.route("/transaction_history/<address>")
def transaction_history(address):
    receiver, sender = get_transactions(address)
    transactions = db2json({ "name":"transaction_history",
                             "address":address,
                             "receiver": receiver,
                             "sender": sender })
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
    unspent = [x for x in receiver if not x['txid'] in spent_ids]
    ans_total, anc_total = [sum([amount_sent(address, id_, x["vout"]) for x in unspent]) for id_ in [ANS_ID, ANC_ID]]
    return jsonify({"NEO": ans_total, "GAS": anc_total, "unspent": [info_received_transaction(address, tx) for tx in unspent]})

@application.route("/get_claim/<address>")
def get_claim(address):
    receiver, sender = get_transactions(address)
    past_claims = get_past_claims(address)
    spent_ids = get_vin_txids(sender)
    claim_ids = get_claimed_txids(past_claims)
    valid_claims = [tx for tx in receiver if is_valid_claim(tx, address, spent_ids, claim_ids)]
    block_diffs = []
    for tx in valid_claims:
        obj = {"txid": tx["txid"]}
        obj["start"] = tx["block_index"]
        info = info_received_transaction(address, tx)
        obj["value"] = info["value"]
        obj["index"] = info["index"]
        when_spent = spent_ids[tx["txid"]]
        obj["end"] = when_spent["block_index"]
        obj["claim"] = int(8.0 * (obj["end"]-obj["start"]) * obj["value"])
        block_diffs.append(obj)
    total = sum([x["claim"] for x in block_diffs])
    return jsonify({"total_claim":total, "claims": block_diffs})

if __name__ == "__main__":
    application.run(host='0.0.0.0')
