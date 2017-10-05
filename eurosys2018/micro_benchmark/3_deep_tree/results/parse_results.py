import tarfile
import os
import sys
import re
import pprint
import base58
import hashlib
import numpy as np

colors = {
  'dns': "#80ba43",
  'dht k1': "#8c46df",
  'dht k1 noprovide': "#888098",
  'dht k2': "#b8daff",
  'dht k2 noprovide': "#f68e5f",
  'dht k3': "#f49e4c",
  'dht k4': "#1b3864"
}
arrows = [
  [250, 250, 250],
  [500, 83, 83, 83, 83, 83],
  [667, 83, 167],
  [750]
]

nodes_mapping = [
 'QmR8aLzU9ZwBfWTAZbZwebnoRxgPhpLewLv4jz1U2VRsBj',
 'QmVsMKfCSJCUupnoqoAMd9HhycyjqsY9ztJ4wzf4jmyBWN',
 'Qmeha9ciXWoLSQXkMAk89YeTmWgLiEacXPH8HU1XePfJs1',
 'QmXvunJC6crSe9yW2ok5Q7dP3wxZ4NunzxucbCfij6kX9g',
 'QmZBhUmDNPvLQaekJnppRNy98yNAbfgfCZKcf1iiLkWwy8'
] # in the order of the sites

topology_mapping = [
 [0, 1, 2, 1, 3], # to go from site 1 to site 1, there is 0 hops, 3 hops to go from site 1 to site 2
 [1, 0, 1, 2, 2],
 [2, 1, 0, 3, 1],
 [1, 2, 3, 0, 4],
 [3, 2, 1, 4, 0]
]

hops_memory = {}

def reject_outliers(data):
  m = 2
  u = np.mean(data)
  s = np.std(data)
  filtered = [e for e in data if (u - 2 * s < e < u + 2 * s)]
  return filtered

object_mapping = {}
def prepare_mapping(objects, trials):
  for object in range(objects):
    for trial in range(trials):
      objname = bytes('object%d%dx0t%d.site1.example.com' % (object, objects, trial), 'ascii')
      sha = b'\x12 ' + hashlib.sha256(objname).digest()
      hash = str(base58.b58encode(sha))
      object_mapping[hash] = {'trial': trial, 'object': object}


def count_none(results, objects, trials, reads):
  c = 0
  for system in results:
    for trial in range(trials):
      for read in range(reads):
        for object in range(objects):
          if results[system][trial][read][object] is None:
            c += 1
  return c

def sort(results, objects, trials, reads):
  for system in results:
    for trial in range(trials):
      for read in range(reads):
        results[system][trial][read] = sorted([results[system][trial][read][object] for object in range(objects) if results[system][trial][read][object] is not None])
        if len(results[system][trial][read]) < objects:
          for j in range(objects-len(results[system][trial][read])):
            results[system][trial][read].append(None)

def fill_blank(results, objects, trials, reads):
  for system in results:
    for trial in range(trials):
      for read in range(reads):
        for object in range(objects):
          if results[system][trial][read][object] is None:
            objects_to_update = [object]
            v = []
            previous_object = object-1
            while previous_object >= 0:
              if results[system][trial][read][previous_object] is not None:
                v.append(results[system][trial][read][previous_object])
                break
              objects_to_update.append(previous_object)
              previous_object -= 1
            following_object = object+1
            while following_object < objects:
              if results[system][trial][read][following_object] is not None:
                v.append(results[system][trial][read][following_object])
                break
              objects_to_update.append(previous_object)
              following_object += 1
            if v == []:
              v = [0.0]


            step = float(( np.max(v)-np.min(v) ) / (len(objects_to_update) +1))
            objects_to_update = sorted(objects_to_update)
            for i, o in enumerate(objects_to_update):
              results[system][trial][read][o] = ((i+1)*step) + np.min(v)


def find_object(line, objects, trial, read, system):
  took_r = re.compile(b'\(([^\)]+)')
  rr = took_r.search(line)
  if rr is not None and rr.group(1).startswith(b'object'):
    r = re.search(b'object([0-9]+)x', rr.group(1) )
    if None != r :
      r = r.group(1)
      r = int(r[:-(len(str(objects)))])
      return r
    else:
      return None
  elif rr is not None and rr.group(1).startswith(b'Qm'):
    hash = rr.group(1).decode('ascii')
    if hash not in object_mapping:
      # try to look for the closest hash
      best_hash = None;
      best_length = 0;
      for hash_ in object_mapping:
        l = 0;
        for i  in range(len(hash)):
          if hash[i] == hash_[i]:
            l += 1
        if l > best_length and l > 2:
          best_length = l;
          best_hash = hash_
      if best_hash == None:
        print('error hash not found %s' % hash)
        return None
      else:
        return object_mapping[best_hash]['object']
    return object_mapping[hash]['object']
  else:
    print('error', line)
  return None

def filters(results, trials, reads, objects):
  for system in results:
    for read in range(reads):
      for object in range(objects):
        r = [results[system][trial][read][object] for trial in range(trials) if results[system][trial][read][object] is not None]
        rf = reject_outliers(r)
        for trial in range(trials):
          if results[system][trial][read][object] not in rf:
            results[system][trial][read][object] = None

def mean(results, trials, reads, objects):
  for system in results:
    print("%s |" % (system), end='')
    for read in range(reads):
      r = [np.mean([results[system][trial][read][object] for object in range(objects) if results[system][trial][read][object] is not None]) for trial in range(trials) ]
      print(" %.3f (±%.3f) |" % (np.mean(r), np.std(r)), end='')
    print('')


def corr(results, car1, car2, trials, reads, objects):
  for system in results['find']:
    corrs = []
    for read in range(reads):
      for object in range(objects):
        x = [results[car1][system][trial][read][object] for trial in range(trials)]
        y = [results[car2][system][trial][read][object] for trial in range(trials)]
        if len(x) > len(y):
          size = len()
        else:
          size = len(x)
        x_ = []
        y_ = []
        for i in range(size):
          if x[i] is not None and y[i] is not None:
            x_.append(x[i])
            y_.append(y[i])
        if len(x_) == 0:
          continue
        corr = np.corrcoef(x_,y_)[0][1]
        if np.isnan(corr):
          continue
        corrs.append(corr)
    print("%s -> %.3f" % (system, np.mean(corrs)))


def graphs(results, max, trials, reads, objects, prefix):
  for read in range(reads):
    results_sorted = {}
    for system in results:
      results_sorted[system] = []
      for object in range(objects):
        r = [results[system][trial][read][object] for trial in range(trials) if results[system][trial][read][object] is not None]
        results_sorted[system].append((np.mean(r), np.std(r)))

    for object in range(objects):
      with open('%s/read%d.obj%d.dat' % (prefix, read,  object), 'w') as f:
        for trial in range(trials):
          f.write("%d\t" % trial)
          for system in results:
            if results[system][trial][read][object] is None:
              f.write("NaN\t")
            else:
              f.write("%.3f\t" % results[system][trial][read][object])
          f.write("\n")

    with open('%s/read%d.unsort.dat' % (prefix, read), 'w') as f:
      for object in range(objects):
        f.write("%d\t" % (object))
        for system in results:
          f.write("%.3f\t%.3f\t" % (results_sorted[system][object][0], results_sorted[system][object][1]))
        f.write('\n')

    for system in results:
      results_sorted[system] = sorted([i for i in results_sorted[system] if False == np.isnan(i[0]) ])
      if len(results_sorted[system]) < objects:
        for j in range(objects-len(results_sorted[system])):
          results_sorted[system].append((np.nan, np.nan))

    with open('%s/read%d.sort.dat' % (prefix, read), 'w') as f:
      for object in range(objects):
        f.write("%d\t" % (object))
        for system in results:
          f.write("%.3f\t%.3f\t" % (results_sorted[system][object][0], results_sorted[system][object][1]))
        f.write('\n')

  with open('%s/read.plot' % (prefix), 'w') as f:
    f.write(
"#!/usr/bin/gnuplot\n" \
"reset\n" \
"fontsize = 18\n" \
"set term png font arial 14 size 1920,1080\n" \
"set encoding utf8\n" \
"set style fill solid 1.0\n" \
"set style data histogram\n" \
"set grid ytics\n" \
"set xlabel \"Object\"\n" \
"set ylabel \"Time to find the metadata (s)\"\n" \
"set xrange [0:" + str(objects) + "]\n" \
"set yrange [0.01:%d]\n" % (max))
    for read in range(reads):
      # unsorted
      f.write("set output 'read%d.unsort.png'\n" % (read))
      f.write("unset arrow\n")
      f.write("plot 'read%d.unsort.dat'" % (read))
      col = 2
      for system in results:
        if col > 2:
          f.write(",\\\n     ''              ")
        label = system.replace('dns', 'DNS').replace('dht', 'DHT')
        f.write(" using %d ti \"%s\" lc rgb \"%s\"" % (col, label, colors[system]))
        col += 2
      f.write("\n\n")
    # sorted
    for read in range(reads):
      f.write("set output 'read%d.sort.png'\n" % (read))
      f.write("unset arrow\n")
      a =0;
      for arrow in arrows[read]:
        a += arrow
        f.write("set arrow from %d, graph 0 to %d, graph 1 nohead front\n" % (a, a))
      f.write("plot 'read%d.sort.dat'" % (read))
      col = 2
      for system in results:
        if col > 2:
          f.write(",\\\n     ''              ")
        label = system.replace('dns', 'DNS').replace('dht', 'DHT')
        f.write(" using %d ti \"%s\" lc rgb \"%s\"" % (col, label, colors[system]))
        col += 2
      f.write("\n\n")


def hops_for_object(system, host, object, trial, read, line):
  hops_r = re.compile(b'([0-9]+) hops')
  hops = hops_r.search(line)
  if hops is None:
    return None
  hops = int(hops.group(1))-1
  if hops in hops_memory[system][read][trial][object]:
    return 0, True
  hops_memory[system][read][trial][object].append(hops)
  return hops, False


def hops_for_object2(system, host, object, trial, read, line):
  hops_r = re.compile(b'([0-9]+) hops')
  nodes_r = re.compile(b'\[(.+)\]')
  contacted_node = nodes_r.search(line)
  if contacted_node is None:
    return None
  contacted_node = str(contacted_node.group(1), 'ascii')
  local_site = host
  remote_site = nodes_mapping.index(contacted_node)
  hops = topology_mapping[local_site][remote_site]
  if (local_site, remote_site) in hops_memory[system][read][trial][object]:
    return 0, True
  hops_memory[system][read][trial][object].append((local_site, remote_site))
  return hops, False


def parse_filename(filename):
  trial_r = re.compile('_trial([0-9])_')
  read_r = re.compile('__([0-9])_read.txt')
  site_r = re.compile('_site([0-9])_')
  try:
    trial = trial_r.search(filename).group(1);
  except:
    trial = None
  try:
    read = read_r.search(filename).group(1);
  except:
    read = None
  try:
    site = site_r.search(filename).group(1);
  except:
    site = None
  return int(trial), int(site), int(read)

def extract(systems, trials, reads, objects):
  results = {'put': {}, 'find': {}, 'hops': {}, 'lhops': {}}
  for s in systems:
    hops_memory[s] = [ [[[] for o in range(objects) ] for t in range(trials) ] for r in range(reads) ]
    for op in ['put', 'find', 'hops', 'lhops']:
      results[op][s] = [[[None for o in range(objects)] for r in range(reads)] for t in range(trials)];
  for s in systems:
    tar = tarfile.open(systems[s])
    for filename in tar.getmembers():
      filename_p = os.path.basename(filename.name)
      if not filename_p.startswith('log_'):
        continue
      if filename_p.endswith('write.txt'):
        continue
      trial, site, read = parse_filename(filename_p)
      if trial == None or read == None:
        print('error with %s' % (filename_p))
        continue
      if trial >= trials:
        continue
      f=tar.extractfile(filename)
      content=f.read()

      findprovidersasync_r = re.compile(b'findprovidersasync_ took ([0-9.]+)([^\ ]+) \(')
      provides_r = re.compile(b'provides took ([0-9.]+)([^\ ]+) \(')
      hops_r = re.compile(b'lookup ([0-9.]+) hops')
      sendrequest_r = re.compile(b'GET_PROVIDERS')
      for line in bytes(content).split(b'\n'):
        op = None
        object = None
        time = None
        unit = None
        if line.startswith(b'sendrequest'):
          op = 'hops'
          r = sendrequest_r.search(line)
          if None == r:
            print('error with %s ' % line)
            continue
          object = find_object(line, objects, trial, read, s)
          if object is None:
            print('->error with %s' % (str(line)))
            continue
          time, duplicate = hops_for_object2(s, site, object, trial, read, line)
          lhops = 1
          if duplicate == True:
            continue

        elif line.startswith(b'lookup') and 'dns' == s:
          op = 'hops'
          r = hops_r.search(line)
          if None == r:
            print('error with %s ' % line)
            continue
          object = find_object(line, objects, trial, read, s)
          if object is None:
            print('->error with %s' % (str(line)))
            continue
          time, duplicate  = hops_for_object(s, site, object, trial, read, line)
          lhops = time
          if duplicate == True:
            continue

        elif line.startswith(b'provides took'):
          op = 'put'
          r = provides_r.search(line)
          if None == r:
            print('error with %s ' % line)
            continue
          time = float(r.group(1))
          unit = r.group(2)
          object = find_object(line, objects, trial, read, s)
          if object is None:
            print('->error with %s' % (str(line)))
            continue
          if b'ms' == unit:
            time /= 1000;
          elif b'\xc2\xb5s' == unit:
            time /= 1000000;
          elif b's' == unit:
            time /= 1;
          else:
            print('unit not known %s' % str(unit))

        elif line.startswith(b'findprovidersasync_ took'):
          op = 'find'
          r = findprovidersasync_r.search(line)
          if None == r:
            print('error with %s ' % line)
            continue
          time = float(r.group(1))
          unit = r.group(2)
          object = find_object(line, objects, trial, read, s)
          if object is None:
            print('->error with %s' % (str(line)))
            continue
          if b'ms' == unit:
            time /= 1000;
          elif b'\xc2\xb5s' == unit:
            time /= 1000000;
          elif b's' == unit:
            time /= 1;
          else:
            print('unit not known %s' % str(unit))

        if op is None:
          continue

        ss = s

        if 'hops' == op:
          if results['lhops'][ss][trial][read][object] is not None:
            results['lhops'][ss][trial][read][object] += lhops
          else:
            results['lhops'][ss][trial][read][object] = lhops

        if results[op][ss][trial][read][object] is not None:
          e = results[op][ss][trial][read][object]
          if 'hops' == op:
            results[op][ss][trial][read][object] += time
          else:
            results[op][ss][trial][read][object] = np.mean([e, time])
        else:
          results[op][ss][trial][read][object] = time

  tar.close()
  for s in systems:
    for trial in range(trials):
      for read in range(reads):
        for object in range(objects):
          if results['hops'][s][trial][read][object] is None and results['find'][s][trial][read][object] is not None:
            results['hops'][s][trial][read][object] = 0.0

  return results

def main():
  trials = 10
  objects = 1000
  reads = 4

  for dir in ['per_object', 'per_rank', 'hops_per_object', 'hops_per_rank', 'lhops_per_object', 'lhops_per_rank']:
    for f in os.listdir(dir):
      if not os.path.isfile(os.path.join(dir, f)):
        print("%s is not a file" % (os.path.join(dir, f)))
        sys.exit(1)
      if not f.endswith('.dat') and not f.endswith('.png') and f != 'read.plot':
        print("%s is not a file we created" % (os.path.join(dir, f)))
        sys.exit(1)
    for f in os.listdir(dir):
      os.remove(os.path.join(dir, f))
    os.rmdir(dir)
    os.mkdir(dir)

  prepare_mapping(objects, trials)
  results = extract({
   'dht k1': 'dht_k1_20171003.tar.gz',
   'dht k2': 'dht_k2_20171003.tar.gz',
   'dht k3': 'dht_k3_20171003.tar.gz',
   'dns': 'dns_20170927.tar.gz',
  }, trials, reads, objects)

  filters(results['find'], trials, reads, objects)
  fill_blank(results['hops'], objects, trials, reads)
  fill_blank(results['lhops'], objects, trials, reads)
  fill_blank(results['find'], objects, trials, reads)


  print("=== find ===")
  mean(results['find'], trials, reads, objects)
  print("=== put ===")
  mean(results['put'], trials, reads, objects)
  graphs(results['find'], 3, trials, reads, objects, 'per_object')
  graphs(results['hops'], 6, trials, reads, objects, 'hops_per_object')
  graphs(results['lhops'], 3, trials, reads, objects, 'lhops_per_object')
#  corr(results, 'find', 'hops', trials, reads, objects)

  sort(results['hops'], objects, trials, reads)
  sort(results['lhops'], objects, trials, reads)
  sort(results['find'], objects, trials, reads)
  graphs(results['find'], 3, trials, reads, objects, 'per_rank')
  graphs(results['hops'], 6, trials, reads, objects, 'hops_per_rank')
  graphs(results['lhops'], 3, trials, reads, objects, 'lhops_per_rank')


if '__main__' == __name__:
  main()

