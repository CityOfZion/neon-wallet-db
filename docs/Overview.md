# Architecture Overview

There are three main components:

* Web process: runs the web server component of the API
* Worker process: processes jobs on the request queue (processing income blockchain data)
* Clock: manage blockchain sync (add jobs to process new blocks)

The `Procfile` in the root of the application defines the commands to run each of these components. In general, the API needs multiple web and worker processes, but only one clock process. One way of doing this is to launch a load balancer over a set of independent AWS servers running web processes. The worker processes connect to a shared redis store to read jobs from the queue -- these do not need to handle any incoming requests. Similarly, the clock process can execute independently to read data from the blockchain and write jobs to the redis queue.

The application also requires a number of environment variables:

* MEMCACHIER_PASSWORD: password for caching service
* MEMCACHIER_SERVERS: server for caching service
* MEMCACHIER_USERNAME: user for caching service
* MONGOHQ_URL: url to mongodb cluster
* MONGOPASS: db password
* MONGOUSER: db username
* NET: which network is it running on?
* REDISTOGO_URL: route to redis store

To install the libraries run

    pip install -r requirements.txt

If you have installed the heroku toolkit you can run:

    heroku local:web # start web server

Or:

    heroku local # start all processes
