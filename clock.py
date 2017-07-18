from apscheduler.schedulers.blocking import BlockingScheduler
from rq import Queue
from worker import conn
from blockchain import sync_blockchain, sync_block

q = Queue(connection=conn)

sched = BlockingScheduler()

@sched.scheduled_job('interval', seconds=10)
def timed_job():
    q.enqueue(sync_blockchain)

sched.start()
