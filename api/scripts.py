from .db import db

transaction_db = db['transactions']
blockchain_db = db['blockchain']
meta_db = db['meta']

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
