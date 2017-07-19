# Lessons learned interacting with NEO block data

This is a work in progress. More will appear here soon.

## ContractTransactions

Transactions of type `ContractTransaction` send assets (e.g., NEO, GAS) over the chain. A transaction type is defined under the `"type"` key for in transaction block data. Other common transaction types are, for example, `ClaimTransaction` and `MinerTransaction`.

For `ContractTransaction`s `"vin"` and `"vout"` are the most important fields as they define how much of an asset will be sent, where it comes from, and where it will go. The `"vin"` field defines a list of transactions, formerly received by the sender, that will now be used to send an asset to the receiver. The `"vout"` field defines a list of addresses and amounts where the sum of the assets in `"vin"` will be sent. For example:

```
{...
"vin": [
        {
          "txid": "fa38ee2e95fca05cc2e37572ce21d8117169b6233358ad0d3b8955a79cd2fa39",
          "vout": 1
        }
      ]
"vout": [
      {
        "address": "AU2CRdjozCr1LKmAAs32BVdyyM7RWcQQTA",
        "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
        "n": 0,
        "txid": "d94440d6fca3c9e1120d103618b0ec638bf34edaa30b0d3e1ac2af8a80bffb56",
        "value": "1"
      },
      {
        "address": "ANrL4vPnQCCi5Mro4fqKK1rxrkxEHqmp2E",
        "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
        "n": 1,
        "txid": "d94440d6fca3c9e1120d103618b0ec638bf34edaa30b0d3e1ac2af8a80bffb56",
        "value": "649"
      }
    ]
...}
```

### How do you know who is sending?

While the receiver addresses are clear from `"vout"`, it is not immediately obvious who is sending the assets. The `"vin"` field provides a list objects that contain transaction ids, but as we have just seen, transactions often deposit assets in multiple accounts, so transaction ids are not enough to know where the assets are originating from. However, each object in the `"vin"` list also provides a `"vout"` parameter (e.g. `transaction["vin"][0]["vout"]`). This parameter defines an index that maps onto the `"vout"` field in its paired transaction (e.g., `transaction["vin"][0]["txid"]`), and so indirectly it can be used to tell us: (1) what address the asset is being sent from, and (2) the amount for that transaction that will now be sent.

As the light wallet database served by this API processes new blocks on the chain, it *automatically adds this information to transaction block data* through the field `"vin_verbose"`. For example:

```
{...
"vin": [
        {
          "txid": "fa38ee2e95fca05cc2e37572ce21d8117169b6233358ad0d3b8955a79cd2fa39",
          "vout": 1
        }
      ]
"vin_verbose": [
        {
          "address": "ANrL4vPnQCCi5Mro4fqKK1rxrkxEHqmp2E",
          "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
          "n": 1,
          "txid": "fa38ee2e95fca05cc2e37572ce21d8117169b6233358ad0d3b8955a79cd2fa39",
          "value": "650"
        }
      ]
...}
```

### How much of an asset is being sent?

The sum of the asset amounts referenced by each input transaction id in `"vin"` (under the sender's address) will be sent in this transaction. For this reason, to send a precise amount of an asset change will often be sent to the receiver. For instance, in the example above, you can see that the sender's address (`ANrL4vPnQCCi5Mro4fqKK1rxrkxEHqmp2E`) also appears in `"vout"`. This means that while 650 total NEO will be sent, 649 will go back to the sender, for a total difference of 1 NEO going to the receiver `AU2CRdjozCr1LKmAAs32BVdyyM7RWcQQTA`.
