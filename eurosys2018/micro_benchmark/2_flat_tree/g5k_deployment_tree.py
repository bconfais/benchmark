# kadeploy3 -f "$OAR_NODE_FILE" -e jessie-x64-nfs -k
# g5k-subnets 
# oarsub -t deploy -l "slash_22=1+{cluster in ('paravance')}/nodes=13,walltime=2:00:00" -r '2017-03-07 12:07:01'
# don't forget the  /switch=1 when using less than half of the cluster
# oarsub -t deploy -l "slash_22=1+{cluster in ('paravance')}/switch=1/nodes=8,walltime=2:00:00" -r '2017-06-09 10:10:01'

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
  for i in host['network_adapters']:
    if 'ip' in i:
      return config['prefix']+i['ip'].split('.')[3], i['ip']


def set_ip_thread(site, node):
   ip = node['ip_vlan']
   exec_commands_thread(node, "ip link set up dev %s;ip addr add %s/32 dev eth1"% (config['latencies']['iface'], ip), False)
   commands = ['echo 1 > /proc/sys/net/ipv4/ip_forward']
   if site == 0:
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][1]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][2]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][4]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
   if site == 1:
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][0]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][2]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][4]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
   if site == 2:
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][0]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][1]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][4]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
   if site == 3:
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][0]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][1]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][2]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][4]['dns'][0]['ip_vlan']))
   if site == 4:
     commands.append("ip route add %s/32 dev eth1" % (topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][0]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][1]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
     commands.append("ip route add %s/32 via %s " % (topology['fog'][2]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan']))
#   for command in commands:
   exec_commands_thread(node, ';'.join(commands), False)

def set_ip():
  logging.info('set_ip')
  threads=[];
  for e,site in enumerate(topology['fog']):
    for node in site['storaged']+site['exportd']+site['client']+site['dns']:
      threads.append(Thread(target=set_ip_thread, args=(e, node, )))
  for t in threads:
    t.start()
  for t in threads:
    t.join()

def exec_commands_thread(node, command, stdout):
  cmd = execo.Process('ssh '+str(node['ip_5k'])+' \''+str(command)+'\'').run()
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

def map_nodes(nodes_list):
  n = list(nodes_list)
  topology = {'fog': [], 'dns': [], 'client': []}
  for site in range(len(config['latencies']['between_fog'])):
    s = {}
    s['client'] = []
    s['exportd'] = []
    s['storaged'] = []
    s['dns'] = []
    for i in range(config['site_composition']['client']):
      s['client'].append(n.pop(0))
    for i in range(config['site_composition']['exportd']):
      s['exportd'].append(n.pop(0))
#    for i in range(config['site_composition']['storaged']):
#      s['storaged'].append(n.pop(0))
    for i in range(config['site_composition']['dns']):
      nn = n.pop(0)
      s['dns'].append(nn)
      s['storaged'].append(nn)
    topology['fog'].append(s)
  for site in range(len(config['latencies']['between_dns_and_fog'])):
    topology['dns'].append(n.pop(0))
  topology['client'].append(n.pop(0))
  return topology

def install_bench():
  """install bench"""
  logging.info('Install bench')
  for n in [el for s in topology['fog'] for el in s['client']]+topology['client']:
    execo.Process('scp /home/bconfais/ipfs+dns/bench_logtime.py '+str(n['ip_5k'])+':/tmp/bench_s1.py').run().stdout
    execo.Process('scp /home/bconfais/ipfs+dns/bench_permutation.py '+str(n['ip_5k'])+':/tmp/bench_s2.py').run().stdout

def install_nuttcp():
  """install nuttcp"""
  logging.info('Install nuttcp')
  for n in [el for s in topology['fog'] for el in s['storaged']+s['client']]+[el for el in topology['dns']]+[el for el in topology['client']]:
    execo.Process('scp /home/bconfais/nuttcp-8.1.4.x86_64 '+str(n['ip_5k'])+':/root/nuttcp').run().stdout

def install_curl():
  logging.info('Install curl')
  commands = ['apt-get update; apt-get --yes --force-yes install python-pycurl']
  exec_commands(commands, [el for s in topology['fog'] for el in s['client']]+[el for el in topology['client']])

def install_named():
  """install Bind"""
  logging.info('Install bind.')
  for n in [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]:
    execo.Process('scp -r /home/bconfais/bind '+str(n['ip_5k'])+':/tmp/bind').run().stdout
  commands = [
    'dpkg -i /tmp/bind/*.deb',
    '/etc/init.d/bind9 stop'
  ]
  exec_commands(commands, [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]);
  
def install_ipfs():
  """install the modified ipfs"""
  logging.info('Install IPFS.')
  commands = [
    'umount /tmp'
  ]
  for n in [el for s in topology['fog'] for el in s['storaged']]:
    execo.Process('scp /home/bconfais/ipfs+dns2/ipfs_dns '+str(n['ip_5k'])+':/tmp/ipfs').run().stdout
    execo.Process('scp /home/bconfais/ipfs+dns/ipfs_dns.service '+str(n['ip_5k'])+':/etc/systemd/system/ipfs.service').run().stdout
#    execo.Process('scp /home/bconfais/ipfs+dns/ipfs_dht '+str(n['ip_5k'])+':/tmp/ipfs').run().stdout
#    execo.Process('scp /home/bconfais/ipfs+dns/ipfs_dht_routing3 '+str(n['ip_5k'])+':/tmp/ipfs').run().stdout
#    execo.Process('scp /home/bconfais/ipfs+dns/ipfs_dht_routing2 '+str(n['ip_5k'])+':/tmp/ipfs').run().stdout
#    execo.Process('scp /home/bconfais/ipfs+dns/ipfs_dht.service '+str(n['ip_5k'])+':/etc/systemd/system/ipfs.service').run().stdout
  commands = [
    'mkdir -p '+str(config['rozofs']['mount_dir']),
  ]
  exec_commands(commands, [el for s in topology['fog'] for el in s['storaged']]);



def deploy_ipfs():
  logging.info('Deploy IPFS')
  for isite, site in enumerate(topology['fog']):
    commands = [
      'mount -t tmpfs tmpfs '+str(config['rozofs']['mount_dir']),
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
      '/tmp/ipfs config DNS.Resolver "%s"' % (topology['fog'][3]['dns'][0]['ip_vlan']),
      '/tmp/ipfs config DNS.Site "site%d"' % ((isite+1)),
      '/tmp/ipfs config DNS.Zone "example.com"',
      '/tmp/ipfs config Datastore.StorageMax "500GB"',
      '/tmp/ipfs config Datastore.Path "/tmp/datastore"'
    ]
    exec_commands(commands, site['storaged'])

    commands = ['IPFS_PATH=%s /tmp/ipfs bootstrap rm --all' % config['rozofs']['mount_dir']]
    exec_commands(commands, site['storaged'])
    commands = ['systemctl start ipfs']
    for s in site['storaged']:
      raw_input('next? %s' %(s['ip_5k']))
      exec_commands(commands, [s])
    raw_input('is starting ok?')



  ids = []
  for site in topology['fog']:
    for n in site['storaged']:
      cmd = execo.action.TaktukRemote(
        'grep PeerID /tmp/config | awk \'{print $2}\' | tr -d \'\\t\' | tr -d \',\' | tr -d \'\\n\' | tr -d \'"\' '
        , hosts=[n['node']]
      )
      cmd.run();
      id = '"/ip4/'+str(n['ip_vlan'])+'/tcp/4001/ipfs/'+cmd.processes[0].stdout.replace('\n','')+'"'
      ids.append(id)

  commands = ['export IPFS_PATH='+str(config['rozofs']['mount_dir'])]
#  for id in ids[-2:]:
  for id in ids:
    commands.append('/tmp/ipfs bootstrap add '+str(id)+'')
  print(commands)
  exec_commands(commands, [el for s in topology['fog'] for el in s['storaged']]);
  commands = ['export IPFS_PATH='+str(config['rozofs']['mount_dir'])]
#  for id in ids[-2:]:
  for id in ids:
    commands.append('/tmp/ipfs swarm connect '+id+'')
  exec_commands(commands, [el for s in topology['fog'] for el in s['storaged']]);

def deploy_named():
  logging.info('Deploy named')

  # create config file
  config_ = "" \
"options {\n" \
"    directory \"/tmp/dns/\";\n" \
"    pid-file \"/run/named/named.pid\";\n" \
"    allow-recursion { 0.0.0.0/0; };\n" \
"    allow-transfer { none; };\n" \
"    allow-update { none; };\n" \
"    version none;\n" \
"    hostname none;\n" \
"    server-id none;\n" \
"    minimal-responses yes;\n" \
"    tcp-clients 10000;\n" \
"    cleaning-interval 0;\n" \
"    rate-limit {\n" \
"      exempt-clients { 0.0.0.0/0; };\n" \
"    };\n" \
"};\n\n" \
"zone \"example.com\" IN {\n" \
"        type master;\n" \
"        file \"example.com.zone\";\n" \
"        allow-update {0.0.0.0/0;};\n" \
"};\n"

  with open('named', 'w') as f:
    f.write(config_)
  for n in [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]:
    execo.Process('scp named '+str(n['ip_5k'])+':/etc/bind/named.conf').run().stdout

  config_ = "" \
"# run resolvconf?\n" \
"RESOLVCONF=no\n" \
"# startup options for the server\n" \
"OPTIONS=\"-u bind -n 10000\"\n" 
  with open('named', 'w') as f:
    f.write(config_)
  for n in [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]:
    execo.Process('scp named '+str(n['ip_5k'])+':/etc/default/bind9').run().stdout


  exec_commands(['rm -rf /tmp/dns/example.com.*', 'mkdir -p /tmp/dns', 'mount -t tmpfs tmpfs /tmp/dns'], [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]);




  # create root zone
#  c = ""
#  for isite, site in enumerate(topology['fog']):
#    c = c + "\nsite%d IN A %s" % ((isite+1), site['dns'][0]['ip_vlan'])
#    c = c + "\n*.site%d IN A %s" % ((isite+1), site['dns'][0]['ip_vlan'])
  config_ = "" \
"$TTL 3000\n" \
"example.com.		IN SOA	example.com. example.com. (2017052314 3600 1800 7257600 86400)\n" \
"@ IN NS example.com.\n" \
"@ IN A %s\n" \
"" % (topology['fog'][3]['dns'][0]['ip_vlan'])
  with open('named', 'w') as f:
    f.write(config_)
  for n in range(len(topology['fog'])):
    execo.Process('scp named '+str(topology['fog'][n]['dns'][0]['ip_5k'])+':/tmp/dns/example.com.zone').run().stdout



  config_ = "" \
"$TTL 3000\n" \
"example.com.		IN SOA	example.com. example.com. (2017052314 3600 1800 7257600 86400)\n" \
"@ IN NS example.com.\n" \
"@ IN A %s\n" \
"site1 IN TXT \"%s,%s\"\n" \
"site2 IN TXT \"%s,%s\"\n" \
"site3 IN TXT \"%s,%s\"\n" \
"site4 IN TXT \"%s\"\n" \
"site5 IN TXT \"%s,%s\"\n" \
"" % (topology['fog'][3]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan'], topology['fog'][0]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan'], topology['fog'][1]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan'],topology['fog'][2]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan'], topology['fog'][3]['dns'][0]['ip_vlan'],topology['fog'][4]['dns'][0]['ip_vlan'])
  with open('named', 'w') as f:
    f.write(config_)
  execo.Process('scp named '+str(topology['fog'][3]['dns'][0]['ip_5k'])+':/tmp/dns/example.com.zone').run().stdout




  exec_commands(['chown bind:bind /tmp/dns/example.com.zone', 'systemctl restart bind9'], [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]);


def mount_rozofs():
  """mount rozofs on each storaged"""
  logging.info('Mount rozofs')
  threads = []
  for site in topology['fog']:
    for client in site['storaged']:
      threads.append(
        Thread(target=exec_commands, args=(['rozofsmount -H %s -E %s -o mojThreadWrite=1,mojThreadRead=1 %s' % (str(site['exportd'][0]['ip_5k']), config['rozofs']['data_dir']+'/exports/export-1/' , config['rozofs']['mount_dir'])]
        , [client], ))
      )
  for t in threads:
    t.start()
  for t in threads:
    t.join()
  time.sleep(10)


def set_latencies():
  logging.info('Set latencies.')
  # latency from clients
  for i_,d in enumerate(topology['client']):
    logging.info('\tGlobal clients to any other node.')
    commands = [
      'modprobe ifb numifbs=1',
      'ip link set dev ifb0 up',
      'tc qdisc add dev %s handle ffff: ingress' % (config['latencies']['iface']),
      'tc filter add dev %s parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev ifb0' % (config['latencies']['iface']),
      'tc qdisc add dev %s root handle 1: htb default 10' % (config['latencies']['iface']),
      'tc class add dev %s parent 1: classid 1:10 htb rate 512mbit' % (config['latencies']['iface']),
      'tc qdisc add dev %s parent 1:10 handle 10: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], 10),
      'tc qdisc add dev ifb0 root handle 1: htb default 10',
      'tc class add dev ifb0 parent 1: classid 1:10 htb rate 512mbit'
    ]
    exec_commands(commands, [d])

  for i,dns in enumerate(topology['dns']):
    commands = ['tc qdisc del dev %s root' % (config['latencies']['iface']),
              'tc qdisc add dev %s root handle 1: prio bands %d' % (config['latencies']['iface'], 9)]
    flow = 1
#    for latency in [10, 22, 81, 137, 227, 325, 665, 764, 932]:
#    for latency in [10, 35, 133, 168, 312]:
#    for latency in [10, 35, 146, 294, 307]:
    for latency in [10, 35, 129]:
      commands += [
        'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, flow, latency)
      ]
      for i_,site_ in enumerate(topology['fog']):
        if config['latencies']['between_dns_and_fog'][i][i_] == latency:
           for n in site_['storaged']:
             commands += [
               'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip_vlan']), flow)
             ]
      flow=flow+1;
    exec_commands(commands, [dns])


  for i,site in enumerate(topology['fog']):
    local_servers = site['storaged']+site['exportd'] #+site['dns']
    local_clients = site['client']

#    logging.info('\tLocal clients to any other node.')
#    commands = [
##      'modprobe ifb numifbs=1',
#      'ip link set dev ifb0 up',
#      'tc qdisc add dev %s handle ffff: ingress' % (config['latencies']['iface']),
#      'tc filter add dev %s parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev ifb0' % (config['latencies']['iface']),
#      'tc qdisc add dev %s root handle 1: htb default 10' % (config['latencies']['iface']),
#      'tc class add dev %s parent 1: classid 1:10 htb rate 512mbit' % (config['latencies']['iface']),
#      'tc qdisc add dev %s parent 1:10 handle 10: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], config['latencies']['between_fog'][i][i]),
#      'tc qdisc add dev ifb0 root handle 1: htb default 10',
#      'tc class add dev ifb0 parent 1: classid 1:10 htb rate 512mbit'
#    ]
#    exec_commands(commands, local_clients)


    # servers to other nodes
    commands = ['tc qdisc del dev %s root' % (config['latencies']['iface']),
              'tc qdisc add dev %s root handle 1: prio bands %d' % (config['latencies']['iface'], 9)]

    flow = 0
#    for latency in [932, 764, 665, 325, 227, 137, 81, 22, 10]: #, 22, 81, 137, 227, 325, 665, 764, 932]:
#    for latency in [10, 22, 81, 137, 227, 325, 665, 764, 932]:
#    for latency in [10, 35, 133, 168, 312]:
#    for latency in [10, 35, 146, 294, 307]:
    for latency in [10, 35, 129]:
      commands += [
        'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, flow, latency)
      ]
      for i_,site_ in enumerate(topology['fog']):
        if i != i_ and config['latencies']['between_fog'][i][i_] == latency:
           for n in site_['storaged']:
             commands += [
               'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip_vlan']), flow)
             ]

      for i_,dns in enumerate(topology['dns']):
        if config['latencies']['between_dns_and_fog'][i_][i] == latency:
          commands += [
            'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(dns['ip_vlan']), flow)
          ]
      flow=flow+2;
#        commands += [
#          'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['between_fog'][i][i_])
#        ]
#        for n in site_['client']:
#          commands += [
#            'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip_vlan']), flow)
#          ]
#        flow=flow+1
#        commands += [
#          'tc qdisc add dev %s parent 1:%d handle %d: netem delay %fms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, 0.5)
#        ]
#        for n in site_['storaged']+site_['exportd']:
#          commands += [
#            'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(n['ip_vlan']), flow)
#          ]
#        flow=flow+1
#      else:

#      for i__,s__ in enumerate(topology['client']):
#        commands += [ 'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, 10) ]
#        commands += [ 'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(topology['client'][i__]['ip_vlan']), flow) ]
#        flow=flow+1;
#
#      flow=flow+10;
#      for i__,s__ in enumerate(topology['dns']):
#        commands += [ 'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['between_dns_and_fog'][i__][i]) ]
#        commands += [ 'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(topology['dns'][i__]['ip_vlan']), flow) ]
#        flow=flow+1;
#
      commands += [ 'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, 10) ]
      commands += [ 'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(topology['client'][0]['ip_vlan']), flow) ]
      flow=flow+1;
#      commands += [ 'tc qdisc add dev %s parent 1:%d handle %d: netem delay %dms 0.1ms distribution normal' % (config['latencies']['iface'], flow, (flow+1)*10, config['latencies']['between_dns_and_fog'][0][0]) ]
#      commands += [ 'tc filter add dev %s protocol ip parent 1: prio 3 u32 match ip dst %s/32 flowid 1:%d' % (config['latencies']['iface'], str(topology['dns'][0]['ip_vlan']), flow) ]
#      flow=flow+1;
    exec_commands(commands, local_servers)


#  commands = ['tc qdisc del dev %s root' % (config['latencies']['iface']),
#              'tc qdisc add dev %s root handle 1: prio bands %d' % (config['latencies']['iface'], len(config['latencies']['between_fog'])+len(config['latencies']['between_dns_and_fog'])+3)]



def bench_thread(command,node,filename):
  print(command)
  cmd = execo.action.TaktukRemote(command, hosts=[node['node']]);
  cmd.run();
  file = open(filename, 'w+');
  file.write(cmd.processes[0].stdout);
  file.close();

dummy = None
def prepare_dummy(node):
  command = 'mkdir /tmp/test; mount -t tmpfs tmpfs /tmp/test; dd if=/dev/urandom of=/tmp/dummy count=1 bs=1G iflag=fullblock ; base64 /tmp/dummy | tr -d \'\\n\' > /tmp/test/dummy'
  dummy = Thread(target=exec_commands_thread, args=(node, command, False,))
  dummy.start()

def sync():
  logging.info("Sync")
  time.sleep(10)
#  exec_commands(['/usr/sbin/rndc freeze', '/usr/sbin/rndc thaw'], [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]);
#  time.sleep(3)
#  exec_commands(['/usr/sbin/rndc freeze', '/usr/sbin/rndc thaw'], [el for s in topology['fog'] for el in s['dns']]+[el for el in topology['dns']]);
#  time.sleep(3)
  commands = [
    'sync',
    'echo 3 > /proc/sys/vm/drop_caches',
    'mount -o remount %s' % (config['rozofs']['mount_dir']),
    'iptables -Z',
    'echo "" > /tmp/log',
  ]
  exec_commands(commands, nodes)

def big_empty():
  return;
  logging.info("Big empty")
  commands = [
    'rm -r '+config['rozofs']['mount_dir']+'/blocks/*'
  ]
  exec_commands(commands, [el for s in topology['fog'] for el in s['storaged']])


def iptables_collect():
  logging.info('iptables.')
  commands = []
  for n in nodes:
    commands.append('iptables -A INPUT -s %s -j ACCEPT' % (str(n['ip_vlan'])))
    commands.append('iptables -A INPUT -s %s -j ACCEPT' % (str(n['ip_5k'])))
  exec_commands(commands, nodes)

def iptables_collect_end_thread(node, filename):
  cmd = execo.action.TaktukRemote('iptables -nvL; netstat -s', hosts=[node['node']]);
  cmd.run();
  file = open(filename, 'w+');
  file.write(cmd.processes[0].stdout);
  file.close();

def iptables_collect_end(filename_prefix, filename_suffix):
  logging.info('Collect amount of network traffic')
  threads = []
  for k, site in enumerate(topology['fog']):
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
    for i,s in enumerate(site['dns']):
      threads.append(
        Thread(target=iptables_collect_end_thread, args=(s, '%s_site%d_monitor%d_%s.txt' % (filename_prefix, k, i+len(site['exportd']), filename_suffix),))
      )

  for k, site in enumerate(topology['dns']):
      threads.append(
        Thread(target=iptables_collect_end_thread, args=(s, '%s_dns%d_%s.txt' % (filename_prefix, k, filename_suffix),))
      )

  for k, site in enumerate(topology['client']):
      threads.append(
        Thread(target=iptables_collect_end_thread, args=(s, '%s_dns%d_%s.txt' % (filename_prefix, k, filename_suffix),))
      )

  for t in threads:
    t.start()
  for t in threads:
    t.join()



def log_collect_end_thread(node, filename):
  cmd = execo.action.TaktukRemote('cat /tmp/log', hosts=[node['node']]);
  cmd.run();
  file = open(filename, 'w+');
  file.write(cmd.processes[0].stdout);
  file.close();

def log_collect_end(filename_prefix, filename_suffix):
  logging.info('Collect log')
  threads = []
  for k, site in enumerate(topology['fog']):
    for i,s in enumerate(site['storaged']):
      threads.append(
        Thread(target=log_collect_end_thread, args=(s, '%s_site%d_osd%d_%s.txt' % (filename_prefix, k, i, filename_suffix),))
      )

  for t in threads:
    t.start()
  for t in threads:
    t.join()




def scenario_s1(workload, trial):
  logging.info("Scenario")
  logging.info("%dx%d Trial %d" % (workload['number'], workload['size'], trial))
  threads_write = []
  threads_read = []

  # write locally
  threads_write.append(
    Thread(
      target=bench_thread,
      args=(('cd /tmp/; python2 bench_s1.py write 0 %dx%dt%d.site1.example.com %d %d %s' % (object['number'], object['size'], trial, workload['number'], workload['size']*1000*1000, str(topology['fog'][0]['storaged'][0]['ip_vlan']), )), topology['client'][0],
      ('%dx%d_trial%d_site%d_client%d_write.txt' % (workload['number'], workload['size'], trial, 1, 1)),)
    )
  )

  # read from another site
  for nbread in range(4):
    threads_read.append([])
    threads_read[nbread].append(
      Thread(
        target=bench_thread,
        args=(('cd /tmp/; python2 bench_s1.py read %d %dx%dt%d.site1.example.com %d %d %s' % (nbread, object['number'], object['size'],trial, workload['number'], workload['size']*1000*1000, str(topology['fog'][nbread+1]['storaged'][0]['ip_vlan']), )), topology['client'][0],
        ('%dx%d_trial%d_site%d_client%d_read%d.txt' % (workload['number'], workload['size'], trial, 1, 1, nbread)),)
      )
    )


  time.sleep(3)
  sync()
  for t in threads_write:
    t.start()
  for t in threads_write:
    t.join()
  iptables_collect_end('ipfs_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), 'write')
  log_collect_end('log_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), 'write')

  for nbread in range(4):
    time.sleep(3)
    sync()
    for t in threads_read[nbread]:
      t.start()
    for t in threads_read[nbread]:
      t.join()
    iptables_collect_end('ipfs_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), '%d_read' % (nbread))
    log_collect_end('log_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), '_%d_read' % (nbread))



def scenario_s2(workload, trial):
  logging.info("Scenario")
  logging.info("%dx%d Trial %d" % (workload['number'], workload['size'], trial))
  threads_write = []
  threads_read = []

  # write locally
  threads_write.append(
    Thread(
      target=bench_thread,
      args=(('cd /tmp/; python2 bench_s2.py write 0 %dx%dt%d.site1.example.com %d %d %s %s %s %s' % (object['number'], object['size'], trial, workload['number'],workload['size']*1000*1000, str(topology['fog'][0]['storaged'][0]['ip_vlan']), str(topology['fog'][0]['storaged'][0]['ip_vlan']), str(topology['fog'][0]['storaged'][0]['ip_vlan']), str(topology['fog'][0]['storaged'][0]['ip_vlan']), )), topology['client'][0],
      ('%dx%d_trial%d_site%d_client%d_write.txt' % (workload['number'], workload['size'], trial, 1, 1)),)
    )
  )

  # read from another site
  for nbread in range(4):
    threads_read.append([])
    threads_read[nbread].append(
      Thread(
        target=bench_thread,
        args=(('cd /tmp/; python2 bench_s2.py read %d %dx%dt%d.site1.example.com %d %d %s %s %s %s' % (nbread, object['number'], object['size'],trial, workload['number'], workload['size']*1000*1000, str(topology['fog'][1]['storaged'][0]['ip_vlan']), str(topology['fog'][2]['storaged'][0]['ip_vlan']), str(topology['fog'][3]['storaged'][0]['ip_vlan']), str(topology['fog'][4]['storaged'][0]['ip_vlan']), )), topology['client'][0],
        ('%dx%d_trial%d_site%d_client%d_read%d.txt' % (workload['number'], workload['size'], trial, 1, 1, nbread)),)
      )
    )


  time.sleep(3)
  sync()
  for t in threads_write:
    t.start()
  for t in threads_write:
    t.join()
  iptables_collect_end('ipfs_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), 'write')
  log_collect_end('log_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), 'write')

  for nbread in range(4):
    time.sleep(3)
    sync()
    for t in threads_read[nbread]:
      t.start()
    for t in threads_read[nbread]:
      t.join()
    iptables_collect_end('ipfs_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), '%d_read' % (nbread))
    log_collect_end('log_trial%d_object%dx%d' % (trial, workload['number'], workload['size']), '_%d_read' % (nbread))



def check_deployment():
  logging.info("Check deployment")

  logging.info("Ping local storaged")
  commands = []
  for d in topology['fog'][0]['storaged']:
    commands += ['ping -c 2 %s' % str(d['ip_vlan'])]
  exec_commands(commands, [topology['client'][0]], True);

  logging.info("Ping remote storaged")
  commands = []
  for d in topology['fog'][1]['storaged']:
    commands += ['ping -c 2 %s' % str(d['ip_vlan'])]
  exec_commands(commands, [topology['fog'][0]['storaged'][0]], True);

  commands = ['/root/nuttcp -S']
  exec_commands(commands, [topology['client'][0]], True);

  logging.info("Throughput to the client")
  commands = []
  for d in topology['fog'][0]['storaged']:
    commands += ['/root/nuttcp %s' % str(d['ip_vlan'])]
  exec_commands(commands, [topology['client'][0]], True);


def config_to_file():
  """compatibility for the merging results script"""
  with open('scenario', 'w') as f:
    objs = []
    for o in config['objects']:
      objs.append({'number': o['number'], 'size': o['size'], 'access': 'parallel'})
    arch = []
    num_osd = 0
    num_monitor = 0
    for i,s in enumerate(topology['fog']):
      site = {}
      site['dc'] = i+1
      site['clients'] = []
      for client in s['client']:
        c = {'node': client['node'], 'ip': client['ip_vlan'], 'ip2': client['ip_5k']}
        site['clients'].append(c)
      for cc in topology['client']:
        c = {'node': cc['node'], 'ip': cc['ip_vlan'], 'ip2': cc['ip_5k']}
        site['clients'].append(c)
      site['osds'] = []
      for storaged in s['storaged']:
        c = {'node': storaged['node'], 'ip': storaged['ip_vlan'], 'ip2': storaged['ip_5k']}
        site['osds'].append(c)
        num_osd += 1
      site['monitors'] = [] # reuse monitors key 
      for exportd in s['exportd']:
        c = {'node': exportd['node'], 'ip': exportd['ip_vlan'], 'ip2': exportd['ip_5k']}
        site['monitors'].append(c)
        num_monitor += 1
      for dns in s['dns']:
        c = {'node': dns['node'], 'ip': dns['ip_vlan'], 'ip2': dns['ip_5k']}
        site['monitors'].append(c)
        num_monitor += 1
      arch.append(site)
    for i,s in enumerate(topology['dns']):
      site = {}
      site['dc'] = i+1+len(topology['fog'])
      site['monitors'] = [] # reuse monitors key 
      c = {'node': s['node'], 'ip': s['ip_vlan'], 'ip2': s['ip_5k']}
      site['monitors'].append(c)
      site['osds'] = []
      site['clients'] = []
      num_monitor += 1
      arch.append(site)
#    for i,s in enumerate(topology['client']):
#      site = {}
#      site['dc'] = i+1+len(topology['fog'])
#      site['monitors'] = [] # reuse monitors key 
#      c = {'node': s['node'], 'ip': s['ip_vlan'], 'ip2': s['ip_5k']}
#      site['monitors'] = []
#      site['osds'] = []
#      site['clients'].append(c)
#      num_monitor += 1
#      arch.append(site)

    c = {
      'nodes': {
        'architecture': arch
      },
      'scenario': 's2',
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
    'latencies': {
      'iface': "eth1",
      'between_fog': [
[10, 129, 129, 129, 129],
[35, 10, 35, 35, 35],
[10, 10, 10, 10, 10],
[129, 35, 10, 129, 10],
[129, 129, 129, 129, 10],
 ],
      'between_dns_and_fog': [],
    },
    'site_composition': {
      'storaged': 0,
      'exportd': 0,
      'client': 0,
      'dns': 1 # dns and storaged collocated
    },
    'rozofs': {
      'layout': 0,
      'data_dir': '/tmp/rozo',
      'config_dir': '/etc/rozofs',
      'mount_dir': '/mnt/rozo',
    },
    'prefix': "10.144.8.",
    'trials': 10,
    'objects': [
#     {'number': 1, 'size': 0.256},
#     {'number': 1, 'size': 1},
#     {'number': 1, 'size': 10},
#     {'number': 10, 'size': 0.256},
#     {'number': 10, 'size': 1},
#     {'number': 100, 'size': 0.256},
#     {'number': 100, 'size': 1},
#     {'number': 10, 'size': 10},
#     {'number': 1000, 'size': 0.004},
#     {'number': 10, 'size': 0.004}, # 300*15
     {'number': 1000, 'size': 0.004}, # 300*15
#     {'number': 4500, 'size': 0.256},
#     {'number': 300, 'size': 1},
#     {'number': 10000, 'size': 0.032},
#     {'number': 100, 'size': 1},
#     {'number': 200, 'size': 0.256},
#     {'number': 200, 'size': 1},
#     {'number': 100, 'size': 10},
#     {'number': 1000, 'size': 0.256},
#     {'number': 1000, 'size': 1},
    ]
  }

  nodes = []
  for node in get_oar_job_nodes(oar_job_id=int(sys.argv[1])):
    ip_vlan, ip = get_ip(node)
#    if ip not in ['172.16.96.4']:
    if ip not in []:
      nodes.append({'node': node, 'ip_vlan': ip_vlan, 'ip_5k': ip})
  nodes.sort()
  topology = map_nodes(nodes)
  pprint.pprint(topology)

  raw_input('go')
#  prepare_dummy(topology['client'][0])

#  install_bench()
#  set_ip()
#  install_nuttcp()
#  install_curl()
#  install_named()
#  install_ipfs()
#  raw_input('ok')
#  deploy_named()
#  raw_input('ok')
#  deploy_ipfs()
#  raw_input('ok')
#  iptables_collect()
#  set_latencies()
#  config_to_file()
#  check_deployment()
#  raw_input('go')
  for i_object, object in enumerate(config['objects']):
    big_empty()
    for n in range(5, config['trials']):
#      scenario_s1(object, n)
      scenario_s2(object, n)
#      raw_input('next?')
