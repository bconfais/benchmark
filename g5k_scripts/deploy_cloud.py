# NOTE: to deploy the debian:
# kadeploy3 -f "$OAR_NODE_FILE" -e jessie-x64-nfs -k

import json
import sys
import time
import logging
import pprint
from threading import Thread
import execo
from execo_engine import logger
from execo_g5k import oarsub, OarSubmission, wait_oar_job_start, kadeploy, get_oar_job_info, get_oar_job_nodes, get_oar_job_subnets, get_host_attributes

def get_ip(node):
  """return the ip of the given host"""
  host = get_host_attributes(node);
  nip = 0 # because with some clusters, the ip to use is not the first one
  # for example, change to 0,1 for lyon
  for i in host['network_adapters']:
   if 'ip' in i:
     if nip > len(i['ip']):
       return None
     return i['ip'][nip];

def exec_commands_thread(node, command, stdout):
  cmd = execo.Process('ssh '+str(node['ip'])+' \''+str(command)+'\'').run()
  logging.info('['+str(node)+'] '+str(command))
  if stdout:
    logging.info('['+str(node)+'] '+str(cmd.stdout))
  return;


def exec_commands(commands, nodes, stdout=False):
  """exec commands with ssh (instead of taktuk)"""
  command = ' ; '.join(commands);
  threads=[];
  for node in nodes:
    print(node)
    threads.append(Thread(target=exec_commands_thread, args=(node, command, stdout)))
  for t in threads:
    t.start()
  for t in threads:
    t.join()

def install_ipfs():
  """install the modified ipfs"""
  logging.info('Install IPFS.')
  commands = [
    'umount /tmp'
  ]
##  exec_commands(commands, [el for s in topology for el in s['storaged']]);
  for n in [el for s in topology for el in s['storaged']]+[el for s in cloud for el in s['exportd']]:
#    execo.Process('scp /home/bconfais/ipfs_common_backend_v1a '+str(n['ip'])+':/tmp/ipfs').run().stdout
#    execo.Process('scp /home/bconfais/ipfs_k1_normal '+str(n['ip'])+':/tmp/ipfs').run().stdout
    execo.Process('scp /home/bconfais/ipfs_centralized_metadata_v1c_big_workers_and_no_ratelimiter_2 '+str(n['ip'])+':/tmp/ipfs').run().stdout
#    execo.Process('scp /home/bconfais/ipfs2 '+str(n['ip'])+':/tmp/ipfs').run().stdout
#    execo.Process('scp /home/bconfais/common_ipfs_try '+str(n['ip'])+':/tmp/ipfs').run().stdout
    execo.Process('scp /home/bconfais/ipfs.service '+str(n['ip'])+':/etc/systemd/system/ipfs.service').run().stdout
  commands = [
    'mkdir -p '+str(config['rozofs']['mount_dir']),
##    'mount -o data=writeback,noatime,barrier=0 /dev/sda5 '+str(config['rozofs']['mount_dir'])
  ]
  exec_commands(commands, [el for s in topology for el in s['storaged']]+[el for s in cloud for el in s['exportd']]);


def deploy_ipfs():
  """configure ipfs"""
  logging.info('Deploy IPFS.')
  commands = [
    'export IPFS_PATH='+str(config['rozofs']['mount_dir']),
    'rm /tmp/config',
    'rm -rf /tmp/datastore',
    'systemctl daemon-reload',
    '/tmp/ipfs init',
    '/tmp/ipfs config --json Discovery.MDNS.Enabled false',
    '/tmp/ipfs config --json Gateway.Writable true',
    '/tmp/ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/8080"',
    '/tmp/ipfs config Addresses.API "/ip4/0.0.0.0/tcp/5001"',
    '/tmp/ipfs config Datastore.StorageMax "500GB"',
    '/tmp/ipfs config Cloud.Listen ":1234"',
    '/tmp/ipfs config Datastore.Path "/tmp/datastore"',
    '/tmp/ipfs bootstrap rm --all',
    'systemctl start ipfs'
  ]
  exec_commands(commands, [cloud[0]['exportd'][0]])
  raw_input('is cloud startd?')

  for site in topology:
    commands = [
      'export IPFS_PATH='+str(config['rozofs']['mount_dir']),
      'rm -fr '+str(config['rozofs']['mount_dir'])+'/blocks',
    ]
    exec_commands(commands, [site['storaged'][0]])
    commands = [
      'export IPFS_PATH='+str(config['rozofs']['mount_dir']),
      'rm /tmp/config',
      'rm -rf /tmp/datastore',
      'systemctl daemon-reload',
      '/tmp/ipfs init',
      '/tmp/ipfs config --json Discovery.MDNS.Enabled false',
      '/tmp/ipfs config --json Gateway.Writable true',
      '/tmp/ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/8080"',
      '/tmp/ipfs config Addresses.API "/ip4/0.0.0.0/tcp/5001"',
      '/tmp/ipfs config Datastore.StorageMax "500GB"',
      '/tmp/ipfs config Cloud.Connect "%s:1234"' % cloud[0]['exportd'][0]['ip'],
      '/tmp/ipfs config Datastore.Path "/tmp/datastore"'
    ]
    exec_commands(commands, site['storaged'])

#    raw_input('execute export IPFS_PATH='+str(config['rozofs']['mount_dir'])+' /tmp/ipfs bootstrap rm --all and /tmp/ipfs daemon --routing dht ...')
    commands = ['IPFS_PATH=%s /tmp/ipfs bootstrap rm --all' % config['rozofs']['mount_dir']]
    exec_commands(commands, site['storaged'])
#    commands = ['rm -f %s/api' % (str(config['rozofs']['mount_dir'])), 'systemctl start ipfs']
    commands = ['systemctl start ipfs']
    for s in site['storaged']:
      time.sleep(2)
      exec_commands(commands, [s])
    raw_input('is starting ok?')

def install_rozofs():
  """install rozofs on each site"""
  logging.info('Install rozofs.')
  for n in [el for s in topology for el in s['storaged']+s['exportd']+s['client']]:
    execo.Process('scp -r /home/bconfais/rozodeb '+str(n['ip'])+':/tmp/rozodeb').run().stdout
#    execo.Process('scp -r /home/bconfais/rozobuild '+str(n['ip'])+':/tmp/rozofs').run().stdout

  commands = [
    'dpkg -i /tmp/rozodeb/*.deb',
#    'cd /tmp/rozofs/build; make install',
    'pkill rozo',
    'pkill storaged',
    'pkill exportd',
  ]
  exec_commands(commands, [el for s in topology for el in s['storaged']+s['exportd']+s['client']]);
  commands = [
    'umount /home',
    'umount /grid5000',
    'mkdir -p '+str(config['rozofs']['data_dir']),
    'mount -t tmpfs tmpfs '+str(config['rozofs']['data_dir']),
#    'umount /tmp',
#    'mount -o data=writeback,noatime,barrier=0 /dev/sda5 /tmp',
    'mkdir -p '+str(config['rozofs']['config_dir']),
  ]
  exec_commands(commands, [el for s in topology for el in s['storaged']+s['exportd']]);
  commands = [
    'mkdir -p '+str(config['rozofs']['data_dir'])+'/exports/export-1'
  ]
  exec_commands(commands, [el for s in topology for el in s['exportd']]);
  commands = [
    'rm -fr '+str(config['rozofs']['data_dir']),
    'mkdir -p '+str(config['rozofs']['data_dir'])+'/storaged/storage-1/0',
    'mkdir -p '+str(config['rozofs']['data_dir'])+'/storaged/storage-2/0',
    'mkdir -p '+str(config['rozofs']['data_dir'])+'/storaged/storage-1/1',
    'mkdir -p '+str(config['rozofs']['data_dir'])+'/storaged/storage-2/1',
    'mkdir -p '+str(config['rozofs']['mount_dir'])
  ]
  exec_commands(commands, [el for s in topology for el in s['storaged']]);
  commands = [
    'umount /home',
    'umount /grid5000',
    'mkdir -p '+str(config['rozofs']['mount_dir'])
  ]
  exec_commands(commands, [el for s in topology for el in s['client']]);

def deploy_rozofs():
  """  """
  logging.info('Deploy rozofs.')
  for site in topology:
    logging.info("Create exportd config")
    sids = []
    for i,s in enumerate(site['storaged']):
      sids.append("\t\t\t\t\t{sid = %d, host = \"%s\";}\n" % ((i+1), s['ip']))
    config_ = "" \
"layout = %d;\n" \
"volumes = \n" \
"( \n" \
"\t{\n" \
"\t\tvid = 1;\n" \
"\t\tcids=\n" \
"\t\t(\n" \
"\t\t\t{\n" \
"\t\t\t\tcid = 1;\n" \
"\t\t\t\tsids=\n" \
"\t\t\t\t(\n" \
"%s" \
"\t\t\t\t);\n" \
"\t\t\t}\n" \
"\t\t);\n" \
"\t}\n" \
"); \n" \
"exports = (\n" \
"\t{eid = 1; bsize=\"4K\"; root = \"%s\"; md5=\"\"; squota=\"\"; hquota=\"\"; vid=1;}\n" \
");\n" % (config['rozofs']['layout'], ",".join(sids), str(config['rozofs']['data_dir'])+'/exports/export-1')
    with open('export', 'w') as f:
      f.write(config_)
    for e in site['exportd']:
      execo.Process('scp export '+str(e['ip'])+':'+str(config['rozofs']['config_dir'])+'/export.conf').run().stdout
    logging.info("Launch exportd")
    commands = [
      'exportd -c '+str(config['rozofs']['config_dir'])+'/export.conf',
      'rozo agent start'
    ]
    exec_commands(commands, site['exportd']);

    for i,s in enumerate(site['storaged']):
      logging.info("Create storaged config")
      config_ = "" \
"crc32c_check     = True; \n" \
"crc32c_generate  = True; \n" \
"listen = (\n" \
"\t{\n" \
"\t\taddr = \"*\";\n" \
"\t\tport = 41001;\n" \
"\t}\n" \
");\n" \
"storages = (\n" \
"\t{cid = 1; sid = %d; root = \"%s\"; device-total = 1; device-mapper = 1; device-redundancy = 1;}\n" \
");\n" % ((i+1), config['rozofs']['data_dir']+'/storaged/storage-1')
      with open('storage', 'w') as f:
        f.write(config_)
      execo.Process('scp storage '+str(s['ip'])+':'+str(config['rozofs']['config_dir'])+'/storage.conf').run().stdout
    logging.info("Launch storaged")
    commands = [
      'rozo agent start'
    ]
    exec_commands(commands, site['storaged']);
    commands = [
      'rozo node start -E 127.0.0.1'
    ]
    time.sleep(5)
    exec_commands(commands, site['exportd']);

def mount_rozofs():
  """mount rozofs on each client"""
  logging.info('Mount rozofs')
  threads = []
  for site in topology:
    for client in site['storaged']:
      threads.append(
        Thread(target=exec_commands, args=(['rozofsmount -H %s -E %s -o mojThreadWrite=1,mojThreadRead=1 %s' % (str(site['exportd'][0]['ip']), config['rozofs']['data_dir']+'/exports/export-1/' , config['rozofs']['mount_dir'])]
        , [client], ))
      )
  for t in threads:
    t.start()
  for t in threads:
    t.join()
  time.sleep(10)

def mount_normal():
  """mount rozofs on each client"""
  logging.info('Mount ipfs')
  threads = []
  for site in topology:
    for client in site['storaged']:
      threads.append(
#        Thread(target=exec_commands, args=(['mount /dev/sda5 %s' % (config['rozofs']['mount_dir'])]
        Thread(target=exec_commands, args=(['mount -t tmpfs tmpfs '+str(config['rozofs']['mount_dir'])]
        , [client], ))
      )
  for client in [el for s in cloud for el in s['exportd']]:
    threads.append(
#      Thread(target=exec_commands, args=(['mount /dev/sda5 %s' % (config['rozofs']['mount_dir'])]
      Thread(target=exec_commands, args=(['mount -t tmpfs tmpfs '+str(config['rozofs']['mount_dir'])]
      , [client], ))
    )

  for t in threads:
    t.start()
  for t in threads:
    t.join()
  time.sleep(10)

def umount():
  """umount rozofs on each client"""
  logging.info('Umount rozofs')
  threads = []
  for site in topology:
    for client in site['storaged']:
      threads.append(
        Thread(target=exec_commands, args=(['umount %s' % (config['rozofs']['mount_dir'])]
        , [client], ))
      )
  for t in threads:
    t.start()
  for t in threads:
    t.join()

def set_latencies():
  """set latencies between the nodes to simulate a fog site"""
  logging.info('Set latencies.')
  cloud_nodes = [el for s in cloud for el in s['exportd']]
  remote_nodes = [el for s in topology for el in s['client']+s['exportd']+s['storaged']]
  logging.info('\tCloud to sites.')
  flow=2
  commands = ['tc qdisc del dev %s root' % (config['latencies']['iface']),
              'tc qdisc add dev %s root handle 1: prio bands 10' % (config['latencies']['iface']),
              'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lcloud'])
  ]
  for n in remote_nodes:
    commands.append(
      'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
    )
  exec_commands(commands, cloud_nodes)


  for i,site in enumerate(topology):
    local_servers = site['storaged']+site['exportd']
    local_clients = site['client']
#    remote_servers = [s['storaged']+s['exportd'] for j,s in enumerate(topology) if j!=i]
    remote_servers = [el for j,s in enumerate(topology) for el in s['storaged']+s['exportd'] if j!=i]
#    remote_clients = [s['client'] for j,s in enumerate(topology) if j!=i]
    remote_clients = [el for j,s in enumerate(topology) for el in s['client'] if j!=i]

    logging.info('Set latency on site %d.' % (i))

    commands = ['tc qdisc del dev %s root' % (config['latencies']['iface']),
                'tc qdisc add dev %s root handle 1: prio bands 10' % (config['latencies']['iface'])]
    exec_commands(commands, local_clients+local_servers)

    # local client
    # to local servers
    logging.info('\tLocal clients to local servers.')
    commands = []
    flow=2;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['ledge'])
    )
    for n in local_servers:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_clients)

    # to remote servers
    logging.info('\tLocal clients to remote servers.')
    commands = []
    flow=3;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lcore']+config['latencies']['ledge'])
    )
    for n in remote_servers:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_clients)

    # to remote clients
    logging.info('\tLocal clients to remote clients.')
    commands = []
    flow=4;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lcore']+config['latencies']['ledge']+config['latencies']['ledge'])
    )
    for n in remote_clients:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_clients)


    # local servers
    # to local clients
    logging.info('\tLocal servers to local clients.')
    commands = []
    flow=2;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['ledge'])
    )
    for n in local_clients:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_servers)

    # to local servers
    logging.info('\tLocal servers to local servers.')
    commands = []
    flow=3;
    commands.append(
#      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal bandwidth 2000mbit' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lfog'])
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lfog'])
    )
    for n in local_servers:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_servers)

    # to remote servers
    logging.info('\tLocal servers to remote servers.')
    commands = []
    flow=4;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lcore'])
    )
    for n in remote_servers:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_servers)

    # to remote clients
    logging.info('\tLocal servers to remote clients.')
    commands = []
    flow=5;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lcore']+config['latencies']['ledge'])
    )
    for n in remote_clients:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_servers)

    # local clients and servers to cloud
    logging.info('\tLocal nodes to Cloud.')
    commands = []
    flow=6;
    commands.append(
      'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['lcore']+config['latencies']['ledge']+config['latencies']['lcloud'])
    )
    for n in cloud_nodes:
      commands.append(
        'tc filter add dev %s protocol ip parent 1:0 prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip']), flow)
      )
    exec_commands(commands, local_clients+local_servers)



def install_ycsb():
  """install ycsb on clients"""
  logging.info('Install YCSB.')
  for n in [el for s in topology for el in s['client']]:
#    execo.Process('scp /home/bconfais/YCSB_ipfs_random_4nodes.tar.gz '+str(n['ip'])+':/tmp/YCSB_ipfs_random.tar.gz').run().stdout
#    execo.Process('scp /home/bconfais/YCSB_ipfs_random_4nodes_dummyfile.tar.gz '+str(n['ip'])+':/tmp/YCSB_ipfs_random.tar.gz').run().stdout
    execo.Process('scp /home/bconfais/YCSB_ipfs_random_4nodes_cache.tar.gz '+str(n['ip'])+':/tmp/YCSB_ipfs_random.tar.gz').run().stdout
  commands = [
    'apt-get update; apt-get --yes --force-yes install openjdk-8-jre-headless',
    'cd /tmp; tar zxvf YCSB_ipfs_random.tar.gz',
#    'cd /tmp; mv YCSB_ipfs_random_4nodes YCSB',
#    'cd /tmp; mv YCSB_ipfs_random_4nodes_dummyfile YCSB',
    'cd /tmp; mv YCSB_ipfs_random_4nodes_cache YCSB',
  ]
  exec_commands(commands, [el for s in topology for el in s['client']])

def iptables_collect():
  """add an iptables entry to measure the amount of network traffic exchanged"""
  logging.info('iptables.')
  commands = []
  for n in nodes:
    commands.append('iptables -A INPUT -s %s -j ACCEPT' % (str(n['ip'])))
  exec_commands(commands, nodes)

def iptables_collect_end_thread(node, filename):
  cmd = execo.action.TaktukRemote('iptables -nvL', hosts=[node['node']]);
  cmd.run();
  file = open(filename, 'w+');
  file.write(cmd.processes[0].stdout);
  file.close();

def iptables_collect_end(filename_prefix, filename_suffix):
  """collect the amount of network traffic"""
  logging.info('Collect amount of network traffic')
  threads = []
  for k, site in enumerate(topology):
    for i,s in enumerate(site['client']):
      threads.append(
        Thread(target=iptables_collect_end_thread, args=(s, '%s_site%d_client%d_%s.txt' % (filename_prefix, k, i, filename_suffix),))
      )
    for i,s in enumerate(site['storaged']):
      threads.append(
        Thread(target=iptables_collect_end_thread, args=(s, '%s_site%d_osd%d_%s.txt' % (filename_prefix, k, i, filename_suffix),))
      )
    for i,s in enumerate(site['exportd']):
      threads.append(
        Thread(target=iptables_collect_end_thread, args=(s, '%s_site%d_monitor%d_%s.txt' % (filename_prefix, k, i, filename_suffix),))
      )

  for t in threads:
    t.start()
  for t in threads:
    t.join()

def sync():
  """sync"""
  commands = [
    'sync',
    'echo 3 > /proc/sys/vm/drop_caches',
    'mount -o remount %s' % (config['rozofs']['mount_dir']),
    'iptables -Z',
  ]
  exec_commands(commands, nodes)
#  umount()
#  time.sleep(2)
#  mount_normal()
#  mount_rozofs()


def empty():
  commands = [
    'echo "" > /tmp/ids'
  ]
  exec_commands(commands, [el for s in topology for el in s['client']])

def big_empty():
  commands = [
    'rm -r '+config['rozofs']['mount_dir']+'/blocks/*'
  ]
  exec_commands(commands, [el for s in topology for el in s['storaged']])


def ycsb_thread(command,node,filename):
  print(command)
  cmd = execo.action.TaktukRemote(command, hosts=[node['node']]);
  cmd.run();
  file = open(filename, 'w+');
  file.write(cmd.processes[0].stdout);
  file.close();


def s3():
  for i_object, object in enumerate(config['objects']):
    big_empty()
    for trial in range(config['trials']):
      logging.info('Iteration %d' % (trial))
      threads_write = []
      threads_read = []

      ycsb_args = '-p requestdistribution=sequential -p fieldcount=1 -p fieldlength=%d -p recordcount=%d -p operationcount=%d -target %d -threads %d' % (object['size']*1000*1000, object['number'], object['number'], object['number'], object['number'])

      for i_site, site in enumerate(topology):
        for i_client, c in enumerate(site['client']):
          threads_write.append(
            Thread(
              target=ycsb_thread,
#              args=(('cd /tmp/YCSB; ./bin/ycsb load ipfs -p ipfs.host1=%s -p ipfs.host2=%s -p ipfs.host3=%s -p ipfs.host4=%s %s -P workloads/workloadc' % (str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_load.txt' % (i_object, trial, i_site+1, i_client+1)),)
#              args=(('cd /tmp/YCSB; ./bin/ycsb load dummy -p dummy.path=%s %s -P workloads/workloadc' % (str(config['rozofs']['mount_dir']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_load.txt' % (i_object, trial, i_site+1, i_client+1)),)
              args=(('cd /tmp/; python2 bench.py write %d %d %s %s %s %s' % (object['number'], object['size'], str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']),)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_load.txt' % (i_object, trial, i_site+1, i_client+1)),)
            )
          )
          threads_read.append(
            Thread(
              target=ycsb_thread,
#              args=(('cd /tmp/YCSB; ./bin/ycsb run ipfs -p ipfs.host1=%s -p ipfs.host2=%s -p ipfs.host3=%s -p ipfs.host4=%s %s -P workloads/workloadc' % (str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_run.txt' % (i_object, trial, i_site+1, i_client+1)),)
#              args=(('cd /tmp/YCSB; ./bin/ycsb run dummy -p dummy.path=%s %s -P workloads/workloadc' % (str(config['rozofs']['mount_dir']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_run.txt' % (i_object, trial, i_site+1, i_client+1)),)
              args=(('cd /tmp/; python2 bench.py read %d %d %s %s %s %s' % (object['number'], object['size'], str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']),)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_run.txt' % (i_object, trial, i_site+1, i_client+1)),)
            )
          )
          # one client one each site 

      logging.info('Clean /tmp/ids')
      empty()


#      raw_input("write ?\n")

      logging.info('Write %d objects of %dMB with %d clients' % (object['number'], object['size'], len(threads_write)))
      # write on all the sites
      sync()
      for t in threads_write:
        t.start()
      for t in threads_write:
        t.join()
      iptables_collect_end('ipfs_trial%d_object%d' % (trial, i_object), 'postwrite')


#      raw_input("read ?\n")


      logging.info('Read %d objects of %dMB with %d clients' % (object['number'], object['size'], len(threads_read)))
      # read on all the sites
      sync()
      for t in threads_read:
        t.start()
      for t in threads_read:
        t.join()
      iptables_collect_end('ipfs_trial%d_object%d' % (trial, i_object), 'postread')


def s2():
  for i_object, object in enumerate(config['objects']):
    big_empty()
    sleep = 5;
    if 1 == object['number']:
      sleep = 2
    for trial in range(config['trials']):
      logging.info('Iteration %d' % (trial))
      threads_write = []
      threads_first_read = []
      threads_second_read = []

      ycsb_args = '-p requestdistribution=sequential -p fieldcount=1 -p fieldlength=%d -p recordcount=%d -p operationcount=%d -target %d -threads %d' % (object['size']*1000*1000, object['number'], object['number'], object['number'], object['number'])

      for i_site, site in [(0, topology[0])]:
        for i_client, c in enumerate(site['client']):
          threads_write.append(
            Thread(
              target=ycsb_thread,
#              args=(('cd /tmp/YCSB; ./bin/ycsb load ipfs -p ipfs.host1=%s -p ipfs.host2=%s -p ipfs.host3=%s -p ipfs.host4=%s %s -P workloads/workloadc' % (str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_write.txt' % (i_object, trial, i_site+1, i_client+1)),)
              args=(('cd /tmp/; python2 bench.py read %d %d %s %s %s %s' % (object['number'], object['size'], str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']),)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_load.txt' % (i_object, trial, i_site+1, i_client+1)),)
            )
          )
      for i_site, site in [(1, topology[1])]:
        for i_client, c in enumerate(site['client']):
          threads_first_read.append(
            Thread(
              target=ycsb_thread,
#              args=(('cd /tmp/YCSB; ./bin/ycsb run ipfs -p ipfs.host1=%s -p ipfs.host2=%s -p ipfs.host3=%s -p ipfs.host4=%s %s -P workloads/workloadc' % (str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_read.txt' % (i_object, trial, i_site+1, i_client+1)),)
              args=(('cd /tmp/; python2 bench.py read %d %d %s %s %s %s' % (object['number'], object['size'], str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']),)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_run.txt' % (i_object, trial, i_site+1, i_client+1)),)
            )
          )
      for i_site, site in [(1, topology[1])]:
        for i_client, c in enumerate(site['client']):
          threads_second_read.append(
            Thread(
              target=ycsb_thread,
#              args=(('cd /tmp/YCSB; ./bin/ycsb run ipfs -p ipfs.host1=%s -p ipfs.host2=%s -p ipfs.host3=%s -p ipfs.host4=%s %s -P workloads/workloadc' % (str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']), ycsb_args)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_secondread.txt' % (i_object, trial, i_site+1, i_client+1)),)
              args=(('cd /tmp/; python2 bench.py read %d %d %s %s %s %s' % (object['number'], object['size'], str(topology[i_site]['storaged'][0]['ip']), str(topology[i_site]['storaged'][1]['ip']), str(topology[i_site]['storaged'][2]['ip']), str(topology[i_site]['storaged'][3]['ip']),)), topology[i_site]['client'][i_client], ('object%d_trial%d_site%d_client%d_run.txt' % (i_object, trial, i_site+1, i_client+1)),)
            )
          )

      logging.info('Clean /tmp/ids')
      empty()

      logging.info('Write %d objects of %dMB with %d clients' % (object['number'], object['size'], len(threads_write)))
      # write on all the sites
      sync()
      for t in threads_write:
        t.start()
      for t in threads_write:
        t.join()
      iptables_collect_end('ipfs_trial%d_object%d' % (trial, i_object), 'postwrite')

      logging.info('scp')
      execo.Process('scp '+str(topology[0]['client'][0]['ip'])+':/tmp/ids ids').run().stdout
      execo.Process('scp ids '+str(topology[1]['client'][0]['ip'])+':/tmp/ids').run().stdout

      logging.info('Read %d objects of %dMB with %d clients' % (object['number'], object['size'], len(threads_first_read)))
      # read on second site
      sync()
      for t in threads_first_read:
        t.start()
      for t in threads_first_read:
        t.join()
      time.sleep(sleep)
      iptables_collect_end('ipfs_trial%d_object%d' % (trial, i_object), 'postread')


      logging.info('Read %d objects of %dMB with %d clients' % (object['number'], object['size'], len(threads_second_read)))
      # read on the second site
      sync()
      for t in threads_second_read:
        t.start()
      for t in threads_second_read:
        t.join()
      time.sleep(sleep)
      iptables_collect_end('ipfs_trial%d_object%d' % (trial, i_object), 'postsecondread')

def map_nodes(nodes_list):
  """return an allocation of the nodes in the  topology"""
  n = list(nodes_list)
  cloud = [{'exportd': [n.pop(0)], 'storaged': [], 'client': []}]
  topology = []
  for site in range(config['architecture']['nbsites']):
    s = {}
    s['storaged'] = []
    s['exportd'] = []
    s['client'] = []
    if 0 == config['rozofs']['layout']:
        for i in range(4): # four storaged per site
          s['storaged'].append(n.pop(0))
#        s['exportd'].append(n.pop(0)) # no need to add an export on each site
        if (len(n)):
          s['client'].append(n.pop(0))

    topology.append(s)
  return cloud, topology


def get_ip(node):
  """return the ip of the given host"""
  host = get_host_attributes(node);
  num = 0 # because with some clusters, the ip to use is not the first one
  # for example, change to 0,1 for lyon
  for i in host['network_adapters']:
    if 'ip' in i:
      return i['ip'];


def config_to_file():
  """compatibility for the merging results script"""
  with open('scenario', 'w') as f:
    objs = []
    for o in config['objects']:
      objs.append({'number': o['number'], 'size': o['size'], 'access': 'parallel'})
    arch = []
    num_osd = 0
    num_monitor = 0
    for i,s in enumerate(topology):
      site = {}
      site['dc'] = i+1
      site['clients'] = []
      for client in s['client']:
        site['clients'].append(client)
      site['osds'] = []
      for storaged in s['storaged']:
        site['osds'].append(storaged)
        num_osd += 1
      site['monitors'] = [] # reuse monitors key 
      for exportd in s['exportd']:
        site['monitors'].append(exportd)
        num_monitor += 1
      arch.append(site)

    for i,s in enumerate(cloud):
      site = {}
      site['monitors'] = cloud[0]['exportd']
      site['osds'] = []
      site['clients'] = []
      arch.append(site)

    c = {
      'nodes': {
        'architecture': arch
      },
      'scenario': 's3',
      'trials': config['trials'],
      'system': 'ipfs',
      'YCSB': True,
      'latencies': config['latencies'],
      'objects': objs
    }
    a = pprint.pformat(c)
    f.write(a)



if '__main__' == __name__:
  logging.basicConfig(level=logging.DEBUG)

  config = {
    'architecture': {
      'nbsites': 3,
    },
    'rozofs': {
      'layout': 0,
      'data_dir': '/tmp/rozo',
      'config_dir': '/etc/rozofs',
      'mount_dir': '/mnt/rozo',
    },
    'latencies': {
      'iface': 'eth0',
      'lfog':  0.5, #ms
      'ledge': 10, #ms
      'lcore': 50, #ms
      'lcloud': 200, #ms
    },
    'trials': 10,
    'objects': [
      {'number': 1, 'size': 0.256 },
      {'number': 1, 'size': 1 },
      {'number': 1, 'size': 10 },
      {'number': 10, 'size': 0.256 },
      {'number': 10, 'size': 1 },
      {'number': 10, 'size': 10 },
      {'number': 100, 'size': 0.256 },
      {'number': 100, 'size': 1 },
      {'number': 100, 'size': 10 },
#      {'number': 25, 'size': 10 },
      {'number': 1000, 'size': 0.256 },
      {'number': 1000, 'size': 1 },
      {'number': 1000, 'size': 10 },
    ]
  }

  if 2 > len(sys.argv):
    logging.error('no jobid')
    sys.exit(0)

#  nodes = get_oar_job_nodes(oar_job_id=int(sys.argv[1]))
  nodes = []
  for node in get_oar_job_nodes(oar_job_id=int(sys.argv[1])):
    i = get_ip(node)
    if i not in ['172.16.96.46']:
      nodes.append({'node': node, 'ip': i})
  nodes.sort()
  cloud, topology = map_nodes(nodes)

  pprint.pprint(topology)
  pprint.pprint(cloud)

  config_to_file()
  raw_input('go')

  if False:
    install_ipfs()
    mount_normal()
    deploy_ipfs()
    set_latencies()
    iptables_collect()
    sys.exit(0)


  s3()
#  s2()

