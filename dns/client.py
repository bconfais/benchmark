#!/usr/bin/python2
#import requests
import itertools
import pycurl
from StringIO import StringIO
import json
import random
import sys
import time
from threading import Thread, Lock

times = []

def timing(f):
  def wrap(*args):
    time1 = time.time()
    ret = f(*args)
    time2 = time.time()
    if (False != ret):
      times.append(float(time2-time1)*1000.0*1000.0)
    return ret
  return wrap

@timing
def write(node, suffix, i):
  buffer = StringIO()
  t1 = time.time()
  c = pycurl.Curl()
  c.setopt(c.URL, 'http://%s:5001/api/v0/block/put?stream-channel=false&arg=%s' % (node, "object"+str(i)+suffix))
  c.setopt(c.HTTPPOST, [('file', (c.FORM_BUFFERPTR, data[i], c.FORM_CONTENTTYPE, 'text/plain') )])
  c.setopt(c.WRITEDATA, buffer)
  c.perform()
  c.close()
  response = json.loads(buffer.getvalue())
  print(response)
  t2 = time.time()
  return t2-t1

@timing
def read(node, suffix, i, size):
  buffer = StringIO()
  t1 = time.time()
  c = pycurl.Curl()
  c.setopt(c.URL, 'http://%s:5001/api/v0/block/get?stream-channel=false&arg=%s' % (node, "object"+str(i)+suffix))
  c.setopt(c.WRITEDATA, buffer)
  c.perform()
  t2 = time.time()
  c.close()
  s = len(buffer.getvalue())
  print(s)
  return (size==s)

if '__main__' == __name__:

  op = sys.argv[1]
  numread = sys.argv[2]
  suffix = sys.argv[3]
  nb = int(sys.argv[4])
  size = int(sys.argv[5])
  nodes = [sys.argv[6], sys.argv[7], sys.argv[8], sys.argv[9]]
  dummy = '/tmp/test/dummy'

  padding = random.randint(1, 10000)

  threads = []
  data = []

  if 'write' == op:
    with open(dummy, 'r') as f:
      f.seek(padding)
      for i in range(nb):
        data.append(f.read(size))
        threads.append(
          Thread(target=write, args=(nodes[random.randint(1, 100)%len(nodes)], suffix, i,))
        )
  elif 'read' == op:
    ll = list(itertools.permutations(range(4), 4))
    for i in range(nb):
      n = ll[i%len(ll)][int(numread)%4]
      threads.append(
        Thread(target=read, args=(nodes[n], suffix, i, size,))
      )

  start = time.time()
  for t in threads:
    t.start()
  started = time.time()
  for t in threads:
    t.join()

  if 'write' == op:
    op = 'insert'

  mean = float(sum(times)) / float(len(times))
  report = "[%s], Operations, %d\n" % (op.upper(), len(times))
  report += "[%s], Start(us), %d\n" % (op.upper(), start)
  report += "[%s], Started(us), %d\n" % (op.upper(), started)
  report += "[%s], AverageLatency(us), %f\n" % (op.upper(), mean)
  report += "[%s], MinLatency(us), %d\n" % (op.upper(), min(times))
  report += "[%s], MaxLatency(us), %d\n" % (op.upper(), max(times))
  report += "[%s], List, %s" % (op.upper(), str(times))
  print(report)
