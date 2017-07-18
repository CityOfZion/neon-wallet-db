import os
from rq import Worker, Queue, Connection
from api import redis_db as conn

listen = ['high', 'default', 'low']

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
