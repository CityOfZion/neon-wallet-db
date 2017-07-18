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

application = Flask(__name__)

q = Queue(connection=redis_db)

transaction_db = db['transactions']
blockchain_db = db['blockchain']

# return all transactions associated with an address (sending to or sent from)
@application.route("/transaction_history/<address>")
def transaction_history(address):
    reciever = [t for t in transaction_db.find({"type":"ContractTransaction",
                        "vout":{"$elemMatch":{"address":address}}})]
    sender = [t for t in transaction_db.find({"type":"ContractTransaction",
                        "vin_verbose":{"$elemMatch":{"address":address}}})]
    out = json.loads(json.dumps({ "name":"transaction_history",
                     "address":address,
                     "receiver": reciever,
                     "sender": sender}, indent=4, default=json_util.default))
    return jsonify(out)

@application.route("/block_height")
def block_height():
    height = [x for x in blockchain_db.find().sort("index", -1).limit(1)][0]["index"]
    return jsonify({"block_height": height})


if __name__ == "__main__":
    application.run(host='0.0.0.0')
