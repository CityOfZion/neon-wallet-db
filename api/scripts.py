from .db import db
from collections import defaultdict

transaction_db = db['transactions']
blockchain_db = db['blockchain']
meta_db = db['meta']
logs_db = db['logs']
address_db = db['addresses']


def write_batch(batch):
    bulk_write = transaction_db.initialize_unordered_bulk_op()
    for t_ in batch:
        bulk_write.find({"_id": t_["_id"]}).update({"$set": {"sys_fee":t_["sys_fee"], "net_fee":t_["net_fee"]}})
    bulk_write.execute()

def change_fee_types():
    counter = 0
    bulk_write = None
    batch = []
    # type 2 = "string"
    for t in transaction_db.find({"sys_fee": {"$type": 2}}):
        t["sys_fee"] = float(t["sys_fee"])
        t["net_fee"] = float(t["net_fee"])
        batch.append(t)
        if counter % 5000 == 0:
            print(counter)
            if counter != 0:
                write_batch(batch)
                batch = []
        counter += 1
    if len(batch) > 0:
        write_batch(batch)

def update_vin_transactions():
    vin_transactions = transaction_db.find({"$and": [{"vin": {"$ne": []}}, {"vin_verbose":{"$exists": False}}]}).sort("block_index", 1)
    for i,t in enumerate(vin_transactions):
        input_transaction_data = []
        for vin in t["vin"]:
            try:
                lookup_t = transaction_db.find_one({"txid": vin['txid']})
                input_transaction_data.append(lookup_t['vout'][vin['vout']])
                input_transaction_data[-1]['txid'] = vin['txid']
            except:
                print("failed on transaction lookup")
                print(vin['txid'])
        t['vin_verbose'] = input_transaction_data
        if i % 100 == 0:
            print(i, t["block_index"])
        transaction_db.update_one({"txid": t["txid"]}, {"$set": t}, upsert=True)

def update_claim_transactions():
    claim_transactions = transaction_db.find({"type":"ClaimTransaction", "$and": [{"claims": {"$ne": []}}, {"claims_verbose":{"$exists": False}}]}).sort("block_index", 1)
    for i,t in enumerate(claim_transactions):
        input_transaction_data = []
        for claim in t["claims"]:
            try:
                lookup_t = transaction_db.find_one({"txid": claim['txid']})
                input_transaction_data.append(lookup_t['vout'][claim['vout']])
                input_transaction_data[-1]['txid'] = claim['txid']
            except:
                print("failed on transaction lookup")
                print(claim['txid'])
        t['claims_verbose'] = input_transaction_data
        if i % 100 == 0:
            print(i, t["block_index"])
        transaction_db.update_one({"txid": t["txid"]}, {"$set": t}, upsert=True)

def update_claim_key():
    claim_transactions = transaction_db.find({"type":"ClaimTransaction", "$and": [{"claims": {"$ne": []}}, {"claims_keys_v1":{"$exists": False}}]}).sort("block_index", 1)
    for i,t in enumerate(claim_transactions):
        input_transaction_data = []
        for claim in t["claims"]:
            try:
                input_transaction_data.append({"key": "{}_{}".format(claim['txid'], claim['vout'])})
            except:
                print("failed on transaction lookup")
                print(claim['txid'])
        t['claims_keys_v1'] = input_transaction_data
        if i % 100 == 0:
            print(i, t["block_index"])
        transaction_db.update_one({"txid": t["txid"]}, {"$set": t}, upsert=True)

def write_batch_fee(batch):
    bulk_write = blockchain_db.initialize_unordered_bulk_op()
    for info in batch:
        bulk_write.find({"index": info["index"]}).update({"$set": {"sys_fee":info["sys_fee"], "net_fee":info["net_fee"]}})
    bulk_write.execute()

def add_fees():
    max_block = blockchain_db.find().sort("index", -1)[0]["index"]+1
    sys_fees = defaultdict(int)
    net_fees = defaultdict(int)
    total_sys = 0.0
    total_net = 0.0
    transactions = defaultdict(list)
    print("gathering transactions...")
    for i,t in enumerate(transaction_db.find({"$or":[{"sys_fee": {"$gt": 0}}, {"net_fee": {"$gt": 0}}]})):
        transactions[t["block_index"]].append(t)
        if i % 5000 == 0:
            print(i)
    print("calculating fees...")
    for block_i in range(0, max_block + 1):
        for t in transactions[block_i]:
            total_sys += t['sys_fee']
            total_net += t['net_fee']
            if t['sys_fee'] < 0:
                print("negative sysfee!!")
            if t['net_fee'] < 0:
                print("negative netfee!!")
        sys_fees[block_i] = total_sys
        net_fees[block_i] = total_net
    print("computed sys fees")
    write_blocks_data = []
    counter = 0
    # for index in range(0, max_block+1):
    for block in blockchain_db.find({ "sys_fee" : { "$exists" : False } }):
        index = block["index"]
        write_blocks_data.append({"index": index, "sys_fee": sys_fees[index], "net_fee": net_fees[index]})
        if counter % 5000 == 0:
            print(sys_fees[index], net_fees[index])
            print(counter)
            write_batch_fee(write_blocks_data)
            write_blocks_data = []
        counter += 1
    write_batch_fee(write_blocks_data)

def compute_accounts():
    last_block_index = None
    for account in logs_db.find():
        address = account["address"]
        address_data = defaultdict(list)
        print(address)
        for i,t in enumerate(transaction_db.find({"$or":[
            {"vout":{"$elemMatch":{"address":address}}},
            {"vin_verbose":{"$elemMatch":{"address":address}}}
        ]})):
            if 'vin_verbose' in t:
                for tx in t["vin_verbose"]:
                    if tx["address"] == address:
                        address_data["spent"].append({
                            "txid": tx["txid"],
                            "n": tx["n"],
                            "value": tx["value"],
                            "asset": tx["asset"],
                            "block_index": t["block_index"]
                        })
            if 'vout' in t:
                for tx in t["vout"]:
                    if tx["address"] == address:
                        address_data["recieved"].append({
                            "txid": t["txid"],
                            "n": tx["n"],
                            "value": tx["value"],
                            "asset": tx["asset"],
                            "block_index": t["block_index"]
                        })
            if 'claims_verbose' in t:
                for tx in t['claims_verbose']:
                    if tx["address"] == address:
                        address_data["claimed"].append({
                            "txid": tx["txid"],
                            "n": tx["n"],
                            "value": tx["value"],
                            "block_index": t["block_index"]
                        })
        address_db.update_one({"address": address}, {
                "$set": {
                    "spent": address_data["spent"],
                    "recieved": address_data["recieved"],
                    "claimed": address_data["claimed"]
                }
            }, upsert = True)
