from flask import Flask
from flask import jsonify
from bson import json_util
import json
from pymongo import MongoClient
import os

application = Flask(__name__)

MONGOUSER = os.environ.get('MONGOUSER')
MONGOPASS = os.environ.get('MONGOPASS')
MONGOURL = os.environ.get('MONGOURL')
MONGOAPP = os.environ.get('MONGOAPP')
MONGOURL = "mongodb://{}:{}@{}/{}".format(MONGOUSER, MONGOPASS, MONGOURL, MONGOAPP)

client = MongoClient(MONGOURL)
db = client[MONGOAPP]
transaction_db = db['transactions']

@application.route("/transaction_history/<address>")
def transaction_history(address):
    reciever = [t for t in transaction_db.find({"type":"ContractTransaction",
                        "vout":{"$elemMatch":{"address":address}}})]
    sender = [t for t in transaction_db.find({"type":"ContractTransaction",
                        "vin_verbose":{"$elemMatch":{"address":address}}})]
    out = json.loads(json.dumps({ "name":"transaction_history",
                     "address":address,
                     "reciever": reciever,
                     "sender": sender}, indent=4, default=json_util.default))
    return jsonify(out)

if __name__ == "__main__":
    application.run(host='0.0.0.0')
