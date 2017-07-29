# Neon Light Wallet Database API

This code runs a database for [Neon](https://github.com/CityOfZion/neon-wallet) that mirrors the NEO blockchain and serves several APIs that don't exist anywhere else (for example, an API to get the full transaction history associated with an address).

### STATUS: MainNet and TestNet are both fully synced and auto-updating.

## How does this work?

This API and a MongoDB mirror of the Neo blockchain live on Heroku. The public API definition is in `api/api.py`. Code that manages keeping the database in sync with public nodes is in `clock.py` and `api/blockchain.py`.

[APScheduler](http://apscheduler.readthedocs.io/en/latest/) polls the blockchain every 5 seconds (to keep blocks up to date) and executes a repair process (for any potential missing blocks) every 5 minutes. The polling and repair logic are both executed by seperate worker processes under the Python [rq](http://python-rq.org) library to avoid overloading the API. Both the number of wep api servers and the number of workers processing incoming transaction data can be scaled arbitrarily.

## Overview of API

All APIs work on both MainNet (https://testnet-api.neonwallet.com) and TestNet (https://api.neonwallet.com).

### Balance data

Given an address, return the current balance of NEO and GAS, as well as a list of transaction ids and amounts for unspent assets: `https://api.neonwallet.com/v1/address/balance/{address}`. Knowing these unspent transaction ids is important for light wallets because [wallets need them to send assets](/docs/Overview.md)!

For example:

    curl http://testnet-api.neonwallet.com/v1/address/balance/ANrL4vPnQCCi5Mro4fqKK1rxrkxEHqmp2E

This will produce:

```json
{
  "GAS": {
    "balance": 64.00325360000001,
    "unspent": [
      {
        "index": 1,
        "txid": "cbd5151931d5d49a209f41a6a012421573bb3e14fb3558bb649279c07499fdd3",
        "value": 8.0
      },
      {
        "index": 0,
        "txid": "4a38a701099bc61ec38bca03477a2e88d9077267a66062d675105df32ef9924c",
        "value": 10.0
      },
      ...
    ]
  },
  "NEO": {
    "balance": 55,
    "unspent": [
      {
        "index": 1,
        "txid": "9d3658842eb6e61f0913f28689f7977d48e931005c92fde4664dcdde8ea5a745",
        "value": 7
      },
      {
        "index": 1,
        "txid": "d999592d08d6059da23f9ec743574e9cf00d1411c187c96869dfd32decf79a2f",
        "value": 46
      },
      {
        "index": 0,
        "txid": "e391f7bb82a746abb93232d260926fff45c6ade4975dcae2dbd0002f302bdb77",
        "value": 1
      },
      ...
    ]
  },
  "address": "AdWDaCmhPmxgksr2iTVuGcLcncSouV6XGv",
  "net": "TestNet"
}
```

### Transaction data

Get detailed information about a transaction: `http://neo-testnet.herokuapp.com/get_transaction/{txid}`. This is identical to the structure returned by the Node CLI except that `ContractTransactions` have been augmented by `vin_verbose` with extra information about input transactions.  

For example:

    curl http://neo-testnet.herokuapp.com/get_transaction/ec4dc0092d5adf8cdf30eadf5116dbb6f138b2e35ca2f1a26d992d69388e0b95

This produces:

```json
{
  "_id": {
    "$oid": "59700381048252991e506558"
  },
  "attributes": [],
  "block_index": 285873,
  "net_fee": "0",
  "scripts": [
    {
      "invocation": "40bcd8a5787e1027cda3cf03e9d1797bed93363ed3c3ff3b6162c0863ed1b5ad50b932a6cea6bd7ae01b6440dc3b509422614742891f0699454988c1b459c84330",
      "verification": "2102028a99826edc0c97d18e22b6932373d908d323aa7f92656a77ec26e8861699efac"
    }
  ],
  "size": 262,
  "sys_fee": "0",
  "txid": "ec4dc0092d5adf8cdf30eadf5116dbb6f138b2e35ca2f1a26d992d69388e0b95",
  "type": "ContractTransaction",
  "version": 0,
  "vin": [
    {
      "txid": "f584373e6a98a88a13b3a61423550063425b6ae2a95dc6b87b2e1e3f49fb3b98",
      "vout": 1
    }
  ],
  "vin_verbose": [
    {
      "address": "ALq7AWrhAueN6mJNqk6FHJjnsEoPRytLdW",
      "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
      "n": 1,
      "txid": "f584373e6a98a88a13b3a61423550063425b6ae2a95dc6b87b2e1e3f49fb3b98",
      "value": "9746"
    }
  ],
  "vout": [
    {
      "address": "ALpwWoxKLwbfCTkRpK2iXrXpaMHgWGcrDV",
      "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
      "n": 0,
      "value": "900"
    },
    {
      "address": "ALq7AWrhAueN6mJNqk6FHJjnsEoPRytLdW",
      "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
      "n": 1,
      "value": "8846"
    }
  ]
}
```

### Claiming GAS

Current block explorers do not provide a list of the available claims for an address. The light wallet API supports this through: `http://api.neonwallet.com/v1/address/claims/{address}`

For example:

    curl http://testnet-api.neonwallet.com/v1/address/claims/AJ3yzTLc5jebUskHtphKi1rb2FNoZjbpkz

This produces a json object where `claims` provides a list of available GAS claims and `total_claim` provides the total amount of GAS available to claim. These claims are denominated in units of `GAS * 100000000` to support the format required by the network protocol. So you can divide these numbers by `100000000` to get the number of GAS the account would actually receive. For each claim object, `value` corresponds to the number of Neo that generated the claim, `start` and `end` correspond to the starting and ending block heights over which the GAS were generated, `claim` gives the amount of GAS to claim (divided by 100m), `txid` provides the id of the transaction that generates the claim, `sysfee` describes the additional network fees you will receive as part of the claim, and `index` provides the `vout` index for that transaction (necessary to submit a claim over the network).

For now, this API only supports "available claims". For more on this, see the [documentation](/docs/Overview.md#claims).

```json
{
  "address": "AJ3yzTLc5jebUskHtphKi1rb2FNoZjbpkz",
  "claims": [
    {
      "claim": 23488,
      "end": 285098,
      "index": 0,
      "start": 283630,
      "sysfee": 0,
      "txid": "f07c0e6a867c7545dd8afdb49c287b368dec8056414dc0eea43c79fa7451bd49",
      "value": 2
    },
    {
      "claim": 192,
      "end": 285116,
      "index": 0,
      "start": 285104,
      "sysfee": 0,
      "txid": "c18bc2f861645f17eeb1adac441b22b354fe9967745da90eb86247226e553ab2",
      "value": 2
    },
    {
      "claim": 1200,
      "end": 285229,
      "index": 0,
      "start": 285154,
      "sysfee": 0,
      "txid": "26512df25fd21c0b491c01de6e7f07f801230a7e8357f249618f2f92c9e9691a",
      "value": 2
    },
    {
      "claim": 48,
      "end": 285239,
      "index": 0,
      "start": 285236,
      "sysfee": 0,
      "txid": "fc5c7bd07e80d45f1bc48a4bbeac54f46d89cfb3b4c1c670122eb41a9b0e80e6",
      "value": 2
    }
  ],
  "net": "TestNet",
  "past_claims": [],
  "total_claim": 24928
}
```

### Transaction History

Current block explorers such as [antchain.org](http://antchain.org) and the current Node APIs only provide information about *unspent transactions* associated with an address. To claim GAS, light wallets need access to more than just unspent transactions!

Use `https://neo.herokuapp.com/transaction_history/{address}` to get full transaction history for an address:

    curl https://neo.herokuapp.com/transaction_history/AU2CRdjozCr1LKmAAs32BVdyyM7RWcQQTA

This produces a json object with two main keys: `"receiver"` holds all transactions that result in assets being received by the address in question (i.e., where that address appears in `"vout"`), and `"sender"` holds all transactions where an asset was sent by the address in question (i.e., where the transaction id and index pair in `"vin"` corresponds to that address). For more details see the [documentation](/docs/Overview.md).

```json
{
  "address": "AU2CRdjozCr1LKmAAs32BVdyyM7RWcQQTA",
  "name": "transaction_history",
  "receiver": [
    {
      "_id": {
        "$oid": "596f06cff769b427dcff23b4"
      },
      "attributes": [],
      "block_index": 1147002,
      "net_fee": "0",
      "scripts": [
        {
          "invocation": "40c7f767e6190bb333c9f26991110516a19bc540081b8bf69d01129f6289a8650bca02f60a5fb00cd949524955aa29300a45c6a74721ee4f5c79c9cdb73bc692ff",
          "verification": "2103b98c67fa12e293ef004f8e191a656a0fafce28f7ba50667dc2d3a6e6dddb1061ac"
        }
      ],
      "size": 262,
      "sys_fee": "0",
      "txid": "d94440d6fca3c9e1120d103618b0ec638bf34edaa30b0d3e1ac2af8a80bffb56",
      "type": "ContractTransaction",
      "version": 0,
      "vin": [
        {
          "txid": "fa38ee2e95fca05cc2e37572ce21d8117169b6233358ad0d3b8955a79cd2fa39",
          "vout": 1
        }
      ],
      "vin_verbose": [
        {
          "address": "ANrL4vPnQCCi5Mro4fqKK1rxrkxEHqmp2E",
          "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
          "n": 1,
          "txid": "fa38ee2e95fca05cc2e37572ce21d8117169b6233358ad0d3b8955a79cd2fa39",
          "value": "650"
        }
      ],
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
    },
    ...
  ],
  "sender": [
    {
      "_id": {
        "$oid": "596f06cff769b427dcff23bf"
      },
      "attributes": [],
      "block_index": 1147005,
      "net_fee": "0",
      "scripts": [
        {
          "invocation": "404b70f6787ab1fdcbcc3fd6c9f7f2a088aa84bcafd42b3b6fc453a50b3d3aa1f502ca87cba81826dd1f58d95719b2fdb3b3b642c66685b1836192e6f594d16a6a",
          "verification": "21021d9d8206e15aa8a1e911283b28ad6d902c6d99790417e79449282fa4c2beb10eac"
        }
      ],
      "size": 202,
      "sys_fee": "0",
      "txid": "ba6d8dd9e849d1a280ff9c1c559ba77716139cb3246ca05d6452dc05d54cf62c",
      "type": "ContractTransaction",
      "version": 0,
      "vin": [
        {
          "txid": "d94440d6fca3c9e1120d103618b0ec638bf34edaa30b0d3e1ac2af8a80bffb56",
          "vout": 0
        }
      ],
      "vin_verbose": [
        {
          "address": "AU2CRdjozCr1LKmAAs32BVdyyM7RWcQQTA",
          "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
          "n": 0,
          "txid": "d94440d6fca3c9e1120d103618b0ec638bf34edaa30b0d3e1ac2af8a80bffb56",
          "value": "1"
        }
      ],
      "vout": [
        {
          "address": "ANrL4vPnQCCi5Mro4fqKK1rxrkxEHqmp2E",
          "asset": "c56f33fc6ecfcd0c225c4ab356fee59390af8560be0e930faebe74a6daff7c9b",
          "n": 0,
          "txid": "ba6d8dd9e849d1a280ff9c1c559ba77716139cb3246ca05d6452dc05d54cf62c",
          "value": "1"
        }
      ]
    },
    ...
  ]
}
```
