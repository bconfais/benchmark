#!/usr/bin/python2

# Bastien Confais
# CNRS, LS2N, UMR 6004, Polytech Nantes, rue Christian Pauc, BP 50609, 44306 Nantes Cedex 3, France
# bastien.confais@univ-nantes.fr

# script to deploy ceph/cassandra/ipfs on a emulated
# fog architecture
# several FOG sites are emulated by
# setting latencies between nodes
# the metrics measured are the data quantity
# and the time to write or to read data
# NOTE: to deploy debian environment:
# kadeploy3 -f "$OAR_NODE_FILE" -e wheezy-x64-nfs -k

import re
import sys
import time
import logging as logger
import pprint
import random
from threading import Thread
import execo
from execo_engine import logger
from execo_g5k import oarsub, OarSubmission, wait_oar_job_start, kadeploy, get_oar_job_info, get_oar_job_nodes, get_oar_job_subnets, get_host_attributes

# measure the latency to store and read data
# the number of bytes exchanged between hosts

def uniq(seq):
	"""remove duplicates values in a list"""
	seen = set()
	seen_add = seen.add
	return [ x for x in seq if not (x in seen or seen_add(x))]

def get_ip(node):
	"""return the ip of the given host"""
	host = get_host_attributes(node);
	# for example, change to 0,1 for lyon
	for i in host['network_adapters']:
		if 'ip' in i:
			return i['ip'];
	return None;


def exec_commands2_thread(node, command):
	execo.Process('ssh '+str(node)+' '+str(command)).run().stdout
	return;

def exec_commands2(commands, nodes, printable):
	"""exec commands with ssh (instead of taktuk), three nodes per three nodes"""
	command = ' ; '.join(commands);
	m = 12
	threads=range(m);
	for t in range(m):
		threads[t] = None
	i=0;
	for node in nodes:
		threads[i]=Thread(target=exec_commands2_thread, args=(node.address, command))
		i=i+1
		if m <= i:
			for t in threads:
				t.start()
			for t in threads:
				t.join()
			for t in range(m):
				threads[t] = None;
			i=0;
	# wait execute last commands here
	for j in range(i):
		threads[j].start()
	for j in range(i):
		threads[j].join()

def exec_commands(commands, nodes, printable):
	"""execute the list of commands on the nodes"""
	command = ' ; '.join(commands);
	addresses = [n.address for n in nodes];
	logger.info(str(','.join(addresses))+':  command: ' + str(command));
	cmd = execo.action.TaktukRemote(
		command
		, hosts=nodes
	)
	cmd.run();
	if ( True == printable ):
		logger.info(cmd.processes[0].stdout);

	return;

def map_nodes(config):
	"""allocate a physical for each storage node, client and monitor"""
	nodes_list = config['nodes']['list']
	nodes = [];
	i_node = 0;

	num_monitor = 0;
	num_osd = 0;
	num_dc = 1;

	if 'ceph' == config['system']:
		types = ['clients', 'osds', 'monitors'];
	elif 'cassandra' == config['system']:
		types = ['clients', 'osds', 'seeds'];
	elif 'ipfs' == config['system']:
		types = ['clients', 'osds'];

	for site in config['architecture']:
		nodes_site = {}
		for type in types:
			if 'ceph' != config['system'] and 'monitors' == type:
				nodes_site[type] = []
				continue;
			if type in site:
				# customization, we add some parameters to the nodes
				nb = site[type] - (site['seeds'] if ('cassandra' == config['system'] and 'osds' == type and 'seeds' in site) else 0 );
				print(str(nb)+' '+str(type))
				if ( nb <= 0):
					nodes_site[type] = []
					continue;
				nodes_ = nodes_list[i_node:i_node+nb];

				for node in nodes_:
					if 'monitors' == type:
						node['num_monitor']=str(num_monitor);
						num_monitor += 1;
					elif 'osds' == type or 'seeds' == type:
						node['num_osd']=str(num_osd);
						num_osd += 1;

				# with cassandra seeds nodes are osds nodes too
				nodes_site[type] = nodes_
				i_node += nb;
			else:
				nodes_site[type] = []

		# customization
		nodes_site['dc'] = str(num_dc);
		num_dc += 1;

		nodes.append(nodes_site);
	config['nodes']['architecture'] = nodes;
	return;


def install_ycsb(config):
	for ip in [ n['ip'] for site in config['nodes']['architecture'] for n in site['clients'] ]:
			execo.Process('scp /home/bconfais/YCSB.tar.gz '+str(ip)+':/tmp/YCSB.tar.gz').run().stdout
	if 'ipfs' == config['system']:
		java_version = '8'
	else:
		java_version = '7'
	commands = [
		'export http_proxy="http://proxy:3128"; export https_proxy="http://proxy:3128"; apt-get update; apt-get --yes --force-yes install openjdk-'+str(java_version)+'-jre-headless'
		, 'cd /tmp; tar zxvf YCSB.tar.gz'
	]
	exec_commands2(commands, [ n['node'] for site in config['nodes']['architecture'] for n in site['clients'] ], False);

def install_ceph(config):
	nodes=[n['node'] for n in config['nodes']['list']];
	nodes_ip=[n['ip'] for n in config['nodes']['list']];

	logger.info('install ceph');
	for node in nodes_ip:
		execo.Process('scp /home/bconfais/ceph.key '+str(node)+':/tmp/apt.key').run().stdout

	commands = [
		'apt-key add /tmp/apt.key'
		, 'echo "deb http://download.ceph.com/debian-firefly/ wheezy main" > /etc/apt/sources.list.d/ceph.list'
		, 'export http_proxy="http://proxy:3128"; export https_proxy="http://proxy:3128"; apt-get update'
		, 'export http_proxy="http://proxy:3128"; export https_proxy="http://proxy:3128"; apt-get --yes --force-yes install ceph ceph-common ceph-deploy ceph-fs-common ceph-fuse haveged'
	]
	exec_commands2(commands, nodes, False);



def deploy_ceph(config):
	"""function to deploy ceph"""
	install_ceph(config)

	nodes=[n['node'] for n in config['nodes']['list']];
	data_directory = config['ceph']['directories']['data'];
	etc_directory = config['ceph']['directories']['config'];

	# global configuration (for all sites)
	all_monitors = {
		'names': [ 'mon'+str(n['num_monitor']) for site in config['nodes']['architecture'] for n in site['monitors'] ],
		'ips': [ n['ip'] for site in config['nodes']['architecture'] for n in site['monitors'] ],
	}

	configuration = '[global]\\nfsid = "a8b74697-2f14-41f5-9139-82c694325a16"\\nmon initial members = '+ str(','.join(all_monitors['names'])) +'\\nmon host = ' + str(','.join(all_monitors['ips'])) + '\\nauth cluster required = none \\nauth service required = none \\nauth client required = none \\nosd journal size = 1024 \\nfilestore xattr use omap = true \\nosd pool default size = 1 \\nosd pool default min size = 1 \\nosd pool default pg num = 100 \\nosd pool default pgp num = 100 \\nosd crush chooseleaf type = 0 \\n\\n[client] \\nrbd cache = false \\nrbd cache writethrough until flush = false \\nrbd_cache_max_dirty = 0\\n\\n'

	commands = [
		'umount /home'
		, 'umount /grid5000'
		, 'mkdir -p "' + str(etc_directory) + '" '
		, 'mkdir -p "' + str(data_directory) + '" '
		, 'rm -r /var/lib/ceph'
		, 'ln -s \'' + str(data_directory) + '\' /var/lib/ceph'
		, 'echo -e \'' + configuration + '\' | sed -e \'s#\\\\[#[#g\' -e \'s#\\\\]#]#g\' > ' + str(etc_directory) +'/ceph.conf'
        ]
	exec_commands(commands, nodes, False);

	for i_site,site in enumerate(config['nodes']['architecture']):
		logger.info('configure ceph on site '+str(i_site));

		# ips of all monitors with local monitor first
		monitors = {};
		monitors['ips'] = [n['ip'] for n in site['monitors']]+[ n['ip'] if n not in site['monitors'] else None for site_ in config['nodes']['architecture'] for n in site_['monitors'] ]
		monitors['ips'] = [ i for i in monitors['ips'] if i is not None ]
		monitors['names'] = ['mon'+str(n['num_monitor']) for n in site['monitors']]+[ 'mon'+str(n['num_monitor']) if n not in site['monitors'] else None for site_ in config['nodes']['architecture'] for n in site_['monitors'] ]
		monitors['names'] = [ i for i in monitors['names'] if i is not None ]

		local_monitors = {}
		local_monitors['ips'] = [n['ip'] for n in site['monitors']]
		local_monitors['names'] = ['mon'+str(n['num_monitor']) for n in site['monitors']]


		# configure monitors
		for monitor in site['monitors']:
			logger.info('configure monitor '+str(monitor['num_monitor']) );
			commands = [
				'cp '+str(etc_directory)+'/ceph.conf '+str(etc_directory)+'/ceph.conf.orig'
				, 'sed -ie "s/^mon initial members = \\(.*\\),\\(.*\\)$/mon initial members = \\1/" '+str(etc_directory)+'/ceph.conf'
				, 'sed -ie "s/^mon host = \\(.*\\),\\(.*\\)/mon host = \\1/" '+str(etc_directory)+'/ceph.conf'
				, 'sed -i "s#\[global\]#[global]\\npublic_addr = '+str(monitor['ip'])+'#" '+str(etc_directory)+'/ceph.conf'
				, 'mkdir -p \'' + str(data_directory) + '/mon/ceph-mon' + str(monitor['num_monitor'])+'\''
			]
			exec_commands(commands, [monitor['node']], False);
			if '0' == monitor['num_monitor']:
				# configure first monitor
				commands = [
					'monmaptool --create --add mon \'' + str(monitor['ip']) + '\' --fsid a8b74697-2f14-41f5-9139-82c694325a16 \'' + str(etc_directory) + '/monmap\' --clobber'
				]
				exec_commands(commands, [monitor['node']], False);
			else:
				commands = [
					'ceph mon getmap -o \'' + str(etc_directory)+ '/monmap\''
				]
				exec_commands(commands, [monitor['node']], False);

			commands = [
				'ceph-mon --mkfs -i mon' + str(monitor['num_monitor']) +' --monmap ' + str(etc_directory)+ '/monmap'
				, 'touch ' + str(data_directory) + '/mon/ceph-mon' + str(monitor['num_monitor']) + '/done'
				, 'ceph-mon -i mon' + str(monitor['num_monitor'])
			]
			exec_commands(commands, [monitor['node']], False);


			if '0' != monitor['num_monitor']:
				commands = [ 'ceph mon add mon' + str(monitor['num_monitor']) + ' ' + str(monitor['ip']) ]
				exec_commands(commands, [config['nodes']['architecture'][0]['monitors'][0]['node']], False);


		# configure osds
		for osd in site['osds']:
			logger.info('configure osd '+str(osd['num_osd']) );
			commands = [
				'mkdir -p \'' + str(data_directory) + '/osd/ceph-' + str(osd['num_osd']) + '\' '
				, 'sed -ie "s/^mon initial members = \\(.*\\)$/mon initial members = '+str(','.join(local_monitors['names']))+'/" '+str(etc_directory)+'/ceph.conf'
				, 'sed -ie "s/^mon host = \\(.*\\)$/mon host = '+str(','.join(local_monitors['ips']))+'/" '+str(etc_directory)+'/ceph.conf'
				, 'ceph-osd -i ' + str(osd['num_osd']) + ' --mkfs --mkjournal'
				, 'ceph osd create $(cat "' + str(data_directory) + '/osd/ceph-' + str(osd['num_osd']) + '/fsid") '
				, 'ceph-osd -i ' + str(osd['num_osd'])
			]
			exec_commands(commands, [osd['node']], False);

		# configure clients
		for client in site['clients']:
			commands = [
				'sed -ie "s/^mon initial members = \\(.*\\)$/mon initial members = '+str(','.join(local_monitors['names']))+'/" '+str(etc_directory)+'/ceph.conf'
				, 'sed -ie "s/^mon host = \\(.*\\)$/mon host = '+str(','.join(local_monitors['ips']))+'/" '+str(etc_directory)+'/ceph.conf'
			]
			exec_commands(commands, [client['node']], False);


	# define clustermap on the first monitor
	logger.info('set clustermap');
	node = config['nodes']['architecture'][0]['monitors'][0]['node'];
	for site in config['nodes']['architecture']:
		logger.info('create dc');
		exec_commands(['ceph osd crush add-bucket dc' + str(site['dc']) + ' datacenter'], [node], False)
		for osd in site['osds']:
			exec_commands([
				'ceph osd crush add-bucket host' + str(osd['num_osd']) + ' host'
				, 'ceph osd crush create-or-move osd.' + str(osd['num_osd']) + ' 1.0 host=host'+ str(osd['num_osd'])
				, 'ceph osd crush move host' + str(osd['num_osd']) + ' datacenter=dc' + str(site['dc'])
			], [node], False)
		exec_commands(['ceph osd crush move dc' + str(site['dc']) + ' root=default'], [node], False)

	# create pools
	time.sleep(20)
	logger.info('remove default pools')
	exec_commands([
		'ceph osd pool delete data data --yes-i-really-really-mean-it'
		, 'ceph osd pool delete metadata metadata --yes-i-really-really-mean-it'
		, 'ceph osd pool delete rbd rbd --yes-i-really-really-mean-it'
	], [node], False)

	logger.info('create pools')
	for site in config['nodes']['architecture']:
		pool_name = str(config['ceph']['pool_prefix']) + str(site['dc'])
		exec_commands([
			'ceph osd pool create '+ pool_name +' '+str(config['ceph']['nb_pgroups'])+' '+str(config['ceph']['nb_pgroups'])
			, 'ceph osd pool set '+ pool_name +' size '+ str(config['ceph']['replication_level'])
		], [node], False)

	logger.info('check')
	exec_commands(['ceph osd tree; ceph -s'], [node], True)
	raw_input("Press Enter to continue...")

	return;

def install_cassandra(config):
	nodes=[n['node'] for n in config['nodes']['list']];
	nodes_ip=[n['ip'] for n in config['nodes']['list']];

	logger.info('install cassandra');
	for node in nodes_ip:
		execo.Process('scp /home/bconfais/cassandra_'+str(config['cassandra']['version'])+'_all.deb '+str(node)+':/tmp/cassandra_'+str(config['cassandra']['version'])+'_all.deb').run().stdout

	commands = [
		'export http_proxy="http://proxy:3128"; export https_proxy="http://proxy:3128"; apt-get update'
		, 'export http_proxy="http://proxy:3128"; export https_proxy="http://proxy:3128"; apt-get --yes --force-yes install openjdk-7-jre-headless haveged'
		, 'dpkg -i /tmp/cassandra_'+str(config['cassandra']['version'])+'_all.deb'
	]
	exec_commands2(commands, nodes, False);

	# not needed
#	for node in nodes_ip:
#		execo.Process('scp /home/bconfais/cassandra-env.sh '+str(node)+':/etc/cassandra/cassandra-env.sh').run().stdout

	return;


def deploy_cassandra(config):
	"""function to deploy cassandra"""
	install_cassandra(config)

	nodes=[n['node'] for n in config['nodes']['list']];
	etc_directory = str(config['cassandra']['directories']['config']);

	commands = [
		'umount /home'
		, 'umount /grid5000'
		, 'mkdir -p "' + str(etc_directory) + '" '
		, '/etc/init.d/cassandra stop'
		, 'rm -r /var/lib/cassandra/'
		, 'mkdir /var/lib/cassandra/'
		, 'mount /dev/sda5 /var/lib/cassandra/'
		, 'chown cassandra:cassandra /var/lib/cassandra/'
		, 'sed -ie "s/^cluster_name: \\(.*\\)/cluster_name: \''+config['cassandra']['cluster_name']+'\'/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^endpoint_snitch: \\(.*\\)/endpoint_snitch: GossipingPropertyFileSnitch/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^listen_address: localhost/#listen_address: localhost\\nlisten_interface: '+config['latencies']['iface']+'/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^rpc_address: localhost/#rpc_address: localhost\\nrpc_interface: '+config['latencies']['iface']+'/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^read_request_timeout_in_ms: 5000/read_request_timeout_in_ms: 600000/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^write_request_timeout_in_ms: 2000/write_request_timeout_in_ms: 600000/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^range_request_timeout_in_ms: 10000/range_request_timeout_in_ms: 600000/" '+etc_directory+'/cassandra.yaml'
		, 'sed -ie "s/^request_timeout_in_ms: 10000/request_timeout_in_ms: 600000/" '+etc_directory+'/cassandra.yaml'
        ]
	exec_commands2(commands, nodes, False);

	all_seeds_ip = [ n['ip'] for site in config['nodes']['architecture'] for n in site['seeds'] ]

	for i_site,site in enumerate(config['nodes']['architecture']):
		logger.info('configure cassandra on site '+str(i_site));
		seeds = [ n['node'] for n in site['seeds'] ];
		osds = [ n['node'] for n in site['osds'] ];
		seeds_ip = [ n['ip'] for n in site['seeds'] ];
		clients = [ n['node'] for n in site['clients'] ];
		exec_commands([
			'sed -ie "s/- seeds: \\(.*\\)/          - seeds: \\"'+','.join(all_seeds_ip)+'\\"/" '+etc_directory+'/cassandra.yaml'
		], seeds, False)
		exec_commands([
			'sed -ie "s/- seeds: \\(.*\\)/          - seeds: \\"'+','.join(seeds_ip)+'\\"/" '+etc_directory+'/cassandra.yaml'
		], osds, False)

		rack = 1;
		for o in seeds+osds:
			exec_commands([
				'echo -e "dc=dc'+str(site['dc'])+'\\nrack='+str(rack)+'" > '+etc_directory+'/cassandra-rackdc.properties'			
			], [o], False)
			rack = rack+1;

		exec_commands([
			'sed -ie "s/- seeds: \\(.*\\)/          - seeds: \\"'+','.join(seeds_ip)+'\\"/" '+etc_directory+'/cassandra.yaml'
		], clients, False)

	all_seeds = [ n['ip'] for site in config['nodes']['architecture'] for n in site['seeds'] ]
	all_osds = [ n['ip'] for site in config['nodes']['architecture'] for n in site['osds'] ]
	for seed in all_seeds:
		execo.Process('ssh '+str(seed)+' /etc/init.d/cassandra start').run().stdout
		time.sleep(10)
	raw_input('seeds ok?')
	for osd in all_osds:
		execo.Process('ssh '+str(osd)+' /etc/init.d/cassandra start').run().stdout
		time.sleep(10)

	# create keyspaces
	time.sleep(20)
	node = config['nodes']['architecture'][0]['seeds'][0];
	for site in config['nodes']['architecture']:
		exec_commands([
			'cqlsh -e "create keyspace '+config['cassandra']['keyspace_prefix']+site['dc']+' with replication = {\'class\': \'NetworkTopologyStrategy\', \'dc'+str(site['dc'])+'\': \''+str(config['cassandra']['replication_level'])+'\'};" '+str(node['ip'])+''
		], [node['node']], False)

	logger.info('check')
	exec_commands(['nodetool status'], [node['node']], True)
	raw_input("Press Enter to continue...")

	return;


def install_ipfs(config):
	"""install ipfs client"""
	nodes=[n['node'] for n in config['nodes']['list']];
	nodes_ip=[n['ip'] for n in config['nodes']['list']];

	logger.info('install ipfs');
	for node in nodes_ip:
		# when we use kvalue=1
		execo.Process('scp /home/bconfais/ipfs '+str(node)+':/tmp/ipfs').run().stdout

	commands = [
		'chmod +x /tmp/ipfs'
	]
	exec_commands2(commands, nodes, False);
	return;


def deploy_ipfs(config):
	"""deploy ipfs client"""
	install_ipfs(config);

	ids=[]
	for i_site,site in enumerate(config['nodes']['architecture']):
		osds  = [n['node'] for n in site['osds']]
		commands = [
			'pkill ipfs'
			, 'rm -fr /root/.ipfs'
			, '/tmp/ipfs init'
			, '/tmp/ipfs config --json Discovery.MDNS.Enabled false'
			, '/tmp/ipfs config --json Gateway.Writable true'
			, '/tmp/ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/8080"'
			, '/tmp/ipfs config Addresses.API "/ip4/0.0.0.0/tcp/5001"'
#			, '/tmp/ipfs daemon --routing dht'
		]
		exec_commands(commands, osds, False)

	# TODO: prepare a systemd service to avoid this
	raw_input('Eexecute "/tmp/ipfs bootstrap rm --all all; /tmp/ipfs daemon --routing dht" on ipfs nodes...')

	# collect node identifiers and add bootstraps nodes
	for i_site,site in enumerate(config['nodes']['architecture']):
		for osd in site['osds']:
			cmd = execo.action.TaktukRemote(
				'grep PeerID /root/.ipfs/config | awk \'{print $2}\' | tr -d \'\\t\' | tr -d \',\' | tr -d \'\\n\' | tr -d \'"\' '
				, hosts=[osd['node']]
			)
			cmd.run();
			id = '"/ip4/'+osd['ip']+'/tcp/4001/ipfs/'+cmd.processes[0].stdout.replace('\n','')+'"'
			ids.append(id)

	osds = [ n['node'] for site in config['nodes']['architecture'] for n in site['osds'] ]
	command=""
	for id in ids:
		command += '/tmp/ipfs bootstrap add '+id+' ;'
	exec_commands([command], osds, False);
	command=""
	for id in ids:
		command += '/tmp/ipfs swarm connect '+id+' ;'
	exec_commands([command], osds, False);

	raw_input('ok..')

	return

def deploy(config):
	"""function to deploy nodes"""
	if 'ceph' == config['system']:
		deploy_ceph(config);
	elif 'cassandra' == config['system']:
		deploy_cassandra(config);
	elif 'ipfs' == config['system']:
		deploy_ipfs(config);
	return;

def set_latencies_tc(src, dsts, iface):
	"""apply tc rules to set latencies"""
	command = 'tc qdisc del dev '+iface+' root; tc qdisc add dev '+iface+' root handle 1: prio bands 10; '
	exec_commands([command], src, False);
	flow=2;
	for dst,latency in dsts:
		command = 'tc qdisc add dev '+iface+' parent 1:'+str(flow)+' handle '+str((flow+1)*10)+': netem delay '+str(latency)+'ms 0.1ms distribution normal; '
		for ip in list(set(dst)):
			command += 'tc filter add dev '+iface+' protocol ip parent 1:0 prio 3 u32 match ip dst '+str(ip)+'/32 flowid 1:'+str(flow)+' ;'
		exec_commands([command], src, False);
		flow += 1;
	return;

def set_latencies(config):
	"""set latencies between hosts"""
	for i_site,site in enumerate(config['nodes']['architecture']):
		logger.info('configure latencies on site '+str(i_site));


		if 'cassandra' == config['system']:
			osds_on_site = site['seeds']+site['osds']
		else:
			osds_on_site = site['osds']

		if 'monitors' in site:
			monitors_on_site = site['monitors']
		else:
			monitors_on_site = []

		clients_on_site = site['clients']


		if 'cassandra' == config['system']:
			osds_remote = [ n if n not in site['osds']+site['seeds'] else None for site_ in config['nodes']['architecture'] for n in site_['osds']+site_['seeds'] ]
		else:
			osds_remote = [ n if n not in site['osds'] else None for site_ in config['nodes']['architecture'] for n in site_['osds'] ]
		osds_remote = [ i for i in osds_remote if i is not None ]

		if 'monitors' in site:
			monitors_remote = [ n if n not in site['monitors'] else None for site_ in config['nodes']['architecture'] for n in site_['monitors'] ]
			monitors_remote = [ i for i in monitors_remote if i is not None ]
		else:
			monitors_remote = []

		clients_remote = [ n if n not in site['clients'] else None for site_ in config['nodes']['architecture'] for n in site_['clients'] ]
		clients_remote = [ i for i in clients_remote if i is not None ]

		servers_on_site = osds_on_site+monitors_on_site
		servers_remote = osds_remote+monitors_remote

		set_latencies_tc(
			[ n['node'] for n in servers_on_site]
			, [
				( [ n['ip'] for n in servers_on_site], config['latencies']['lfog'])
#				,( [ n['ip'] for n in clients_on_site], config['latencies']['ledge']+config['latencies']['lfog'])
				,( [ n['ip'] for n in clients_on_site], config['latencies']['ledge'])
#				,( [ n['ip'] for n in servers_remote], config['latencies']['lcore']+config['latencies']['lfog']+config['latencies']['lfog'])
				,( [ n['ip'] for n in servers_remote], config['latencies']['lcore']+config['latencies']['lfog']+config['latencies']['lfog'])
#				,( [ n['ip'] for n in clients_remote], config['latencies']['lcore']+config['latencies']['ledge']+config['latencies']['lfog'])
				,( [ n['ip'] for n in clients_remote], config['latencies']['lcore']+config['latencies']['ledge'])
			]
			, config['latencies']['iface']
		)
		set_latencies_tc(
			[ n['node'] for n in clients_on_site]
			, [
#				( [ n['ip'] for n in servers_on_site], config['latencies']['ledge']+config['latencies']['lfog'])
				( [ n['ip'] for n in servers_on_site], config['latencies']['ledge'])
#				,( [ n['ip'] for n in servers_remote], config['latencies']['ledge']+config['latencies']['lcore']+config['latencies']['lfog'])
				,( [ n['ip'] for n in servers_remote], config['latencies']['ledge']+config['latencies']['lcore'])
#				,( [ n['ip'] for n in clients_remote], config['latencies']['ledge']+config['latencies']['lcore']+config['latencies']['ledge'])
				,( [ n['ip'] for n in clients_remote], config['latencies']['ledge']+config['latencies']['lcore'])
			]
			, config['latencies']['iface']
		)


	return;



def collect_iptables_end_(node, filename):
	cmd = execo.action.TaktukRemote('iptables -nvL', hosts=[node]);
	cmd.run();
	file = open(filename, 'w+');
	file.write(cmd.processes[0].stdout);
	file.close();
	return;


def collect_iptables_end(config, i_object, i_trial, post_read_write):
	"""get amount of network traffic"""
	t = []
	for i_site,site in enumerate(config['nodes']['architecture']):
		if 'monitors' in site:
			for i_monitor,monitor in enumerate(site['monitors']):
				t.append(Thread(target=collect_iptables_end_, args=(monitor['node'], '/home/bconfais/' + config['system'] + '_trial' + str(i_trial) + '_object' + str(i_object) + '_site' + str(i_site) + '_monitor' + str(i_monitor) + '_'+post_read_write+'.txt',)))
		if 'seeds' in site:
			for i_seed,seed in enumerate(site['seeds']):
				t.append(Thread(target=collect_iptables_end_, args=(seed['node'], '/home/bconfais/' + config['system'] + '_trial' + str(i_trial) + '_object' + str(i_object) + '_site' + str(i_site) + '_seed' + str(i_seed) + '_'+ post_read_write + '.txt',)))
		for i_osd,osd in enumerate(site['osds']):
			t.append(Thread(target=collect_iptables_end_, args=(osd['node'], '/home/bconfais/' + config['system'] + '_trial' + str(i_trial) + '_object' + str(i_object) + '_site' + str(i_site) + '_osd' + str(i_osd) + '_' + post_read_write + '.txt',)))
		for i_client,client in enumerate(site['clients']):
			t.append(Thread(target=collect_iptables_end_, args=(client['node'], '/home/bconfais/' + config['system'] + '_trial' + str(i_trial) + '_object' + str(i_object) + '_site' + str(i_site) + '_client' + str(i_client) + '_' + post_read_write + '.txt',)))
	for th in t:
		th.start()
	for th in t:
		th.join()

	return;


def configure_iptables(src, dsts):
	"""configure iptables"""
	command=''
	for dst in dsts:
		if [] == dst:
			continue;
		command += 'iptables -A INPUT -s '+ ','.join(list(set(dst))) +' -j ACCEPT; '
	exec_commands([command], src, False)
	return;

def configure_iptables(config):
	"""use iptables to collect the quantity of data"""
	for i_site,site in enumerate(config['nodes']['architecture']):
		logger.info('configure iptables on site '+str(i_site));

		osds_on_site = site['osds']
		if 'seeds' in site:
			osds_on_site += site['seeds']
		if 'monitors' in site:
			monitors_on_site = site['monitors']
		clients_on_site = site['clients']


		osds_remote = [ n if n not in site['osds'] else None for site_ in config['nodes']['architecture'] for n in site_['osds'] ]
		osds_remote = [ i for i in osds_remote if i is not None ]

		if 'seeds' in site:
			osds_remote += [ n if n not in site['seeds'] else None for site_ in config['nodes']['architecture'] for n in site_['seeds'] ]
			osds_remote = [ i for i in osds_remote if i is not None ]
		if 'monitors' in site:
			monitors_remote = [ n if n not in site['monitors'] else None for site_ in config['nodes']['architecture'] for n in site_['monitors'] ]
			monitors_remote = [ i for i in monitors_remote if i is not None ]

		clients_remote = [ n if n not in site['clients'] else None for site_ in config['nodes']['architecture'] for n in site_['clients'] ]
		clients_remote = [ i for i in clients_remote if i is not None ]

		if 'monitors' in site: #ceph
			srcs = [monitors_on_site, osds_on_site, clients_on_site];
			dsts = [[ n['ip'] for n in monitors_on_site], [ n['ip'] for n in monitors_remote], [ n['ip'] for n in osds_on_site], [ n['ip'] for n in osds_remote], [ n['ip'] for n in clients_on_site], [ n['ip'] for n in clients_remote]]
		else:
			srcs = [osds_on_site, clients_on_site];
			dsts = [[ n['ip'] for n in osds_on_site], [ n['ip'] for n in osds_remote], [ n['ip'] for n in clients_on_site], [ n['ip'] for n in clients_remote]]

		src = [n['node'] for src in srcs for n in src]
		configure_iptables(src,dsts)
	return;


def full_sync_thread(config, osd):
	"""to sync all nodes in parallel"""
	logger.info('sync osd '+str(osd['num_osd']) );
	if 'ceph' == config['system']:
		commands = [
			'sync'
			, 'mount -o remount /tmp/'
			, 'echo 3 > /proc/sys/vm/drop_caches'
		]
	elif 'cassandra' == config['system'] or 'ipfs' == config['system']:
		commands = [
			'sync'
			, 'mount -o remount /'
			, 'echo 3 > /proc/sys/vm/drop_caches'
		]
	exec_commands(commands, [osd['node']], False);


def full_sync(config):
	"""flush cache on osds and umount and remount the disk to avoid hotcache"""
	threads = [];
	for i_site,site in enumerate(config['nodes']['architecture']):
		for osd in site['osds']:
			threads.append(Thread(target=full_sync_thread, args=(config, osd,)))
		if 'cassandra' == config['system']:
			for osd in site['seeds']:
				threads.append(Thread(target=full_sync_thread, args=(config, osd,)))
	for t in threads:
		t.start();
	for t in threads:
		t.join();

	return;


def thread_local_ycsb(config, i_objects, i_trial, i_site, i_client, load_run):
	"""launch ycsb on one client and write the output in a file"""

	site = config['nodes']['architecture'][i_site];
	client = site['clients'][i_client];
	filename = 'object'+str(i_objects)+'_trial'+str(i_trial)+'_site'+str(i_site+1)+'_client'+str(i_client+1)+'_'+load_run;
	if 'ceph' == config['system']:
		binding = 'rados';
		args = '-p hosts="'+str(site['monitors'][0]['ip'])+'" -p rados.pool='+str(config['ceph']['pool_prefix']) + str(site['dc'])+' -p rados.configfile=/etc/ceph/ceph.conf';
	elif 'cassandra' == config['system']:
		binding = 'cassandra2-cql';
		args = '-p cassandra.readtimeoutmillis=600000 -p hosts="'+str(site['seeds'][0]['ip'])+'" -p cassandra.keyspace='+config['cassandra']['keyspace_prefix']+site['dc']+'';
	elif 'ipfs' == config['system']:
		binding = 'ipfs';
		args = '-p ipfs.host1='+site['osds'][0]['ip']+' -p ipfs.host2='+site['osds'][1]['ip']+' ';
	args += ' -p fieldcount=1 -p fieldlength='+str(int(config['objects'][i_objects]['size']*1000*1000))+' -p recordcount='+str(config['objects'][i_objects]['number'])+' -p operationcount='+str(config['objects'][i_objects]['number'])+''
	args += ' -p requestdistribution=sequential '

	if 'sequential' == config['objects'][i_objects]['access']:
		command = ['cd /tmp/YCSB; ./bin/ycsb '+load_run+' '+binding+' '+args+'  -P workloads/'+config['workload']+' -threads 1 -target '+str(config['objects'][i_objects]['number'])+' '];
	else:
		command = ['cd /tmp/YCSB; ./bin/ycsb '+load_run+' '+binding+' '+args+'  -P workloads/'+config['workload']+' -threads '+str(config['objects'][i_objects]['number'])+' -target '+str(config['objects'][i_objects]['number'])+' '];

	print(command)

	cmd = execo.action.TaktukRemote(command[0], hosts=[client['node']]);
	cmd.run();
	file = open(filename, 'w+');
	file.write(cmd.processes[0].stdout);
	file.close();


def scenario_local_ycsb(config, i_objects, i_trial):
	"""scenario ycsb: each client write on its site and read that it has written"""

	# reset ipfs and cassandra
	if 'ipfs' == config['system']:
		for s in range(len(config['nodes']['architecture'])):
			if 0 < len(config['nodes']['architecture'][s]['clients']):
				exec_commands(['echo -n "" > /tmp/ids'], [config['nodes']['architecture'][s]['clients'][0]['node']], False);
	elif 'cassandra' == config['system']:
		logger.info('recreate cassandra tables');
		for i_site,site in enumerate(config['nodes']['architecture']):
			node = config['nodes']['architecture'][i_site]['seeds'][0];
			exec_commands([
				'cqlsh -e "use '+config['cassandra']['keyspace_prefix']+site['dc']+'; drop table usertable; create table usertable( y_id varchar primary key, field0 blob );" '+str(node['ip'])+''
			], [node['node']], False)


	# sync
	full_sync(config);
	# reset iptables counters
	nodes=[n['node'] for n in config['nodes']['list']];
	exec_commands2(['iptables -Z'], nodes, False)

	# write
	threads = []
	i=0;
	for i_site,site in enumerate(config['nodes']['architecture']):
		for i_client, client in enumerate(site['clients']):
			threads.append(Thread(target=thread_local_ycsb, args=(config, i_objects, i_trial, i_site, i_client, 'load', )))
			i = i+1;
	for t in threads:
		t.start()
	for t in threads:
		t.join()

	# collect the amount of network traffic
	collect_iptables_end(config, i_objects, i_trial, 'postwrite');
	exec_commands2(['iptables -Z'], nodes, False)
	full_sync(config);

	# read
	threads = [];
	i=0;
	for i_site,site in enumerate(config['nodes']['architecture']):
		for i_client, client in enumerate(site['clients']):
			threads.append(Thread(target=thread_local_ycsb, args=(config, i_objects, i_trial, i_site, i_client, 'run', )))
			i = i+1;
	for t in threads:
		t.start()
	for t in threads:
		t.join()

	# collect the amount of network traffic
	collect_iptables_end(config, i_objects, i_trial, 'postread');

	# reset ceph
	if 'ceph' == config['system']:
		logger.info('recreate ceph pools');
		node = config['nodes']['architecture'][0]['monitors'][0]['node'];
		for site in config['nodes']['architecture']:
			pool_name = str(config['ceph']['pool_prefix']) + str(site['dc'])
			exec_commands([
				'ceph osd pool delete '+ pool_name + ' '+ pool_name +' --yes-i-really-really-mean-it'
				, 'ceph osd pool create '+ pool_name +' '+str(config['ceph']['nb_pgroups'])+' '+str(config['ceph']['nb_pgroups'])
				, 'ceph osd pool set '+ pool_name +' size '+ str(config['ceph']['replication_level'])
				, 'ceph osd pool set '+ pool_name +' crush_ruleset '+str(site['dc'])
			], [node], False)


def thread_remote_ycsb(config, i_objects, i_trial, i_site, i_client, load_run, write_read_secondread):
	"""launch ycsb on one client and write the output in a file"""

	site = config['nodes']['architecture'][i_site];
	client = site['clients'][i_client];
	filename = 'object'+str(i_objects)+'_trial'+str(i_trial)+'_site'+str(i_site+1)+'_client'+str(i_client+1)+'_'+write_read_secondread;
	if 'ceph' == config['system']:
		binding = 'rados';
		args = '-p hosts="'+str(site['monitors'][0]['ip'])+'" -p rados.pool='+str(config['ceph']['pool_prefix']) + str(config['nodes']['architecture'][0]['dc'])+' -p rados.configfile=/etc/ceph/ceph.conf';
	elif 'cassandra' == config['system']:
		binding = 'cassandra2-cql';
		args = '-p cassandra.readtimeoutmillis=600000 -p hosts="'+str(site['seeds'][0]['ip'])+'" -p cassandra.keyspace='+config['cassandra']['keyspace_prefix']+config['nodes']['architecture'][0]['dc']+'';
	elif 'ipfs' == config['system']:
		binding = 'ipfs';
		args = '-p ipfs.host1='+ site['osds'][0]['ip']+' -p ipfs.host2='+ site['osds'][1]['ip']+' ';
	args += ' -p fieldcount=1 -p fieldlength='+str(int(config['objects'][i_objects]['size']*1000*1000))+' -p recordcount='+str(config['objects'][i_objects]['number'])+' -p operationcount='+str(config['objects'][i_objects]['number'])+''
	args += ' -p requestdistribution=sequential '

	if 'sequential' == config['objects'][i_objects]['access']:
		command = ['cd /tmp/YCSB; ./bin/ycsb '+load_run+' '+binding+' '+args+'  -P workloads/'+config['workload']+' -threads 1 -target '+str(config['objects'][i_objects]['number'])+' '];
	else:
		command = ['cd /tmp/YCSB; ./bin/ycsb '+load_run+' '+binding+' '+args+'  -P workloads/'+config['workload']+' -threads '+str(config['objects'][i_objects]['number'])+' -target '+str(config['objects'][i_objects]['number'])+' '];

	print(str(client['ip'])+': '+command[0])

	cmd = execo.action.TaktukRemote(command[0], hosts=[client['node']]);
	cmd.run();
	file = open(filename, 'w+');
	file.write(cmd.processes[0].stdout);
	file.close();


def scenario_remote(config, i_objects, i_trial):
	"""scenario remote ycsb: write on site 0 and read from site 1"""
	logger.info('scenario_remote_ycsb('+str(i_objects)+','+str(i_trial)+')')


	# reset ipfs and cassandra
	if 'ipfs' == config['system']:
		for s in range(len(config['nodes']['architecture'])):
			if 0 < len(config['nodes']['architecture'][s]['clients']):
				exec_commands(['echo -n "" > /tmp/ids'], [config['nodes']['architecture'][s]['clients'][0]['node']], False);
	elif 'cassandra' == config['system']:
		logger.info('recreate cassandra tables');
		for i_site,site in enumerate(config['nodes']['architecture']):
			node = config['nodes']['architecture'][i_site]['seeds'][0];
			exec_commands([
				'cqlsh -e "use '+config['cassandra']['keyspace_prefix']+site['dc']+'; drop table usertable; create table usertable( y_id varchar primary key, field0 blob );" '+str(node['ip'])+''
			], [node['node']], False)


	# sync
	full_sync(config);
	# reset iptables counter
	nodes=[n['node'] for n in config['nodes']['list']];
	exec_commands2(['iptables -Z'], nodes, False)

	# write
	# TODO: use real threads, it works because we have only one client per site and write on only one site
	thread_remote_ycsb(config, i_objects, i_trial, 0, 0, 'load', 'write');

	# collect the amount of network traffic
	collect_iptables_end(config, i_objects, i_trial, 'postwrite');
	exec_commands2(['iptables -Z'], nodes, False)

	# if ipfs is used, we have to copy the list of the keys to the client that will perform the read
	if 'ipfs' == config['system']:
		execo.Process('scp '+str(config['nodes']['architecture'][0]['clients'][0]['ip'])+':/tmp/ids /home/bconfais/ids').run().stdout
		execo.Process('scp /home/bconfais/ids '+str(config['nodes']['architecture'][1]['clients'][0]['ip'])+':/tmp/ids').run().stdout

	full_sync(config);


	# read
	thread_remote_ycsb(config, i_objects, i_trial, 1, 0, 'run', 'read');

	# collect the amount of network traffic
	collect_iptables_end(config, i_objects, i_trial, 'postread');
	exec_commands2(['iptables -Z'], nodes, False)

	thread_s2_ycsb(config, i_objects, i_trial, 1, 0, 'run', 'secondread');
	collect_iptables_end(config, i_objects, i_trial, 'postsecondread');

	# reset ceph
	if 'ceph' == config['system']:
		logger.info('recreate ceph pools');
		node = config['nodes']['architecture'][0]['monitors'][0]['node'];
		for site in config['nodes']['architecture']:
			pool_name = str(config['ceph']['pool_prefix']) + str(site['dc'])
			exec_commands([
				'ceph osd pool delete '+ pool_name + ' '+ pool_name +' --yes-i-really-really-mean-it'
				, 'ceph osd pool create '+ pool_name +' '+str(config['ceph']['nb_pgroups'])+' '+str(config['ceph']['nb_pgroups'])
				, 'ceph osd pool set '+ pool_name +' size '+ str(config['ceph']['replication_level'])
				, 'ceph osd pool set '+ pool_name +' crush_ruleset '+str(site['dc'])
			], [node], False)




def bench(config):
	"""main function for test"""

	# deployment
	set_latencies(config);
	deploy(config);
	prepare_iptables(config);
	install_ycsb(config);


	# benchmark
	for i_trial in range(config['trials']):
		for i_objects,o in enumerate(config['objects']): # each trial and each object configuration
			if 'local' ==  config['scenario']:
				scenario_local(config, i_objects, i_trial)
			elif 'remote' ==  config['scenario']:
				scenario_remote(config, i_objects, i_trial)
	return

if '__main__' == __name__:
	config = {
		'architecture': [
			# we consider that we have x storage_nodes and y monitors or x storage_nodes including z seed nodes (because seed nodes are storage nodes too, unlike monitors)
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
			{ 'monitors': 1, 'seeds': 1, 'osds': 2, 'clients': 1 },
		],
		'latencies': {
			'iface': 'eth0',
			'lfog': 0.5, #ms #not named in the article
			'ledge': 10, #ms #Lfog in the article
			'lcore': 0 #ms
		},
		'objects': [
			# size in MB
			{ 'number': 1, 'size': 0.256, 'access': 'sequential'},
			{ 'number': 1, 'size': 1, 'access': 'sequential'},
			{ 'number': 10,	'size': 0.256, 'access': 'parallel'},
			{ 'number': 400, 'size': 1, 'access': 'parallel'},
			{ 'number': 400, 'size': 10, 'access': 'parallel' },
			{ 'number': 100, 'size': 10, 'access': 'parallel'},
			{ 'number': 1, 'size': 10, 'access': 'sequential'},
			{ 'number': 10, 'size': 1, 'access': 'sequential'},
			{ 'number': 10, 'size': 1, 'access': 'parallel'},
			{ 'number': 400, 'size': 0.256, 'access': 'parallel'},
			{ 'number': 100, 'size': 1, 'access': 'parallel'},
			{ 'number': 10, 'size': 10, 'access': 'parallel'},
			{ 'number': 100, 'size': 0.256, 'access': 'parallel'},
			{ 'number': 100, 'size': 10, 'access': 'parallel'},
			{ 'number': 100, 'size': 0.128, 'access': 'parallel'},
			{ 'number': 1000,'size': 1, 'access': 'parallel'},
			{ 'number': 100, 'size': 64, 'access': 'parallel'},
			{ 'number': 100, 'size': 128, 'access': 'parallel'},
			{ 'number': 100, 'size': 128, 'access': 'parallel'},
			{ 'number': 800, 'size': 0.128, 'access': 'parallel'},
			{ 'number': 1600, 'size': 0.064, 'access': 'parallel'},
			{ 'number': 1, 'size': 0.128, 'access': 'sequential'
			},
		],
		'ceph': {
			'directories': {
				'data': '/tmp/ceph/',
				'config': '/etc/ceph/'
			},
			'nb_pgroups': 150,
			'replication_level': 1,
			'pool_prefix': 'pool_'
		},
		'cassandra': {
			'directories': {
				'config': '/etc/cassandra/'
			},
			'version': '2.1.12',
			'cluster_name': 'Test',
			'replication_level': 1,
			'keyspace_prefix': 'keyspace_',
			'table_prefix': 'table_'
		},
		'system': 'ipfs',
		'workload': 'workloadc',
		'scenario': 'local',
		'trials': 10
	}

	if ( 3 != len(sys.argv) ):
		logger.error(('usage: %s <job_id>' % sys.argv[0]));
		sys.exit(1);

	# determine how many nodes to deploy according to the test settings
	nb_nodes = 0;
	for site in config['architecture']:
		for type in ['clients', 'osds', 'monitors']:
			if 'ceph' != config['system'] and 'monitors' == type:
				continue;
			if 'cassandra' != config['system'] and 'seeds' == type:
				continue;
			if type in site:
				nb_nodes += site[type];

	config['nb_nodes'] = nb_nodes;


	# create the list of computers we have with their ip addresses
	logger.info('get nodes list')
	config['nodes'] = {};
	config['nodes']['list'] = [];
	for node in get_oar_job_nodes(oar_job_id=int(sys.argv[1])):
		ip = get_ip(node)
		config['nodes']['list'].append({'node': node, 'ip': ip});
	config['nodes']['list'].sort()
	map_nodes(config);
	pprint.pprint(config)

	# go
	bench(config);
