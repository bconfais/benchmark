#!/usr/bin/python2
#import requests
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
#    if (0 != ret):
#      times.append(float(ret)*1000.0*1000.0)
    if (False != ret):
      times.append(float(time2-time1)*1000.0*1000.0)
    return ret
  return wrap

@timing
def write(node, id_file, i):
#  response = requests.post('http://%s:5001/api/v0/block/put?stream-channel=true' % node,
#    files={'file': ('file.txt', data, 'text/plain', {})}
#  )
#  
#  id_file[1].acquire()
#  if 200 == response.status_code:
#    id_file[0].write(response.json()['Key']+'\n')
#  id_file[1].release()
  buffer = StringIO()
  t1 = time.time()
  c = pycurl.Curl()
  c.setopt(c.URL, 'http://%s:5001/api/v0/block/put?stream-channel=false' % (node))
  c.setopt(c.HTTPPOST, [('file', (c.FORM_BUFFERPTR, data[i], c.FORM_CONTENTTYPE, 'text/plain') )])
  c.setopt(c.WRITEDATA, buffer)
  c.perform()
  c.close()
  t2 = time.time()
  response = json.loads(buffer.getvalue())
  id_file[1].acquire()
  id_file[0].write(response['Key']+'\n')
  id_file[1].release()
  return t2-t1

@timing
def read(node, key, size):
  buffer = StringIO()
  t1 = time.time()
  c = pycurl.Curl()
  c.setopt(c.URL, 'http://%s:5001/api/v0/block/get?stream-channel=false&arg=%s' % (node, key))
  c.setopt(c.WRITEDATA, buffer)
  c.perform()
  t2 = time.time()
  c.close()
  s = len(buffer.getvalue())
  return (size==s)
#  print('read %d bytes' % s)
#  if (size == s):
#    return t2-t1
#  else:
#    return 0

if '__main__' == __name__:

  op = sys.argv[1]
  nb = int(sys.argv[2])
  size = int(sys.argv[3])
  nodes = [sys.argv[4]]
  dummy = '/tmp/test/dummy'

#  if 'write' == op:
#    random.seed(10)
#  else:
#    random.seed(3)

  padding = random.randint(1, 10000)


  id_file = None
  threads = []

  data = []

  if 'write' == op:
    id_file = [open('/tmp/ids', 'w'), Lock()]
    with open(dummy, 'r') as f:
      f.seek(padding)
      for i in range(nb):
        data.append(f.read(size))
        threads.append(
          Thread(target=write, args=(nodes[random.randint(1, 100)%len(nodes)], id_file, i,))
        )
  elif 'read' == op:
    id_file = [open('/tmp/ids', 'r'), Lock()]
    for i in range(nb):
      threads.append(
        Thread(target=read, args=(nodes[random.randint(1, 100)%len(nodes)], id_file[0].readline().rstrip(), size,))
      )

  start = time.time()
  for t in threads:
    t.start()
  started = time.time()
  for t in threads:
    t.join()
  if 'write' == op:
    id_file[0].close()

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
