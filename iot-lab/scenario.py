from iotlab_testbed import iotlab_testbed
from g5k_testbed import g5k_testbed
from threading import Thread, Lock

class scenario(object):

 def __init__(self, g5k, iotlab):
  self.g5k = g5k
  self.iotlab = iotlab

 def __deploy_g5k(self):
  return
#  self.g5k.use_existing_reservation(1786306)
  self.g5k.book_nodes();
  self.g5k.wait_nodes();
  nodes = self.g5k.get_nodes();
  self.g5k.deployenv_nodes([nodes[0]]);
  self.g5k.install_ipfs(nodes[0]);
  self.g5k.start_ipfs(nodes[0]);
  iotlab_hostname, iotlab_username, iotlab_key, iotlab_password = self.iotlab.get_ssh_params();
  self.g5k.tunnel_g5k_to_iotlab(nodes[0], iotlab_hostname, iotlab_username, iotlab_key, iotlab_password)
  print('everything is ok')
  self.g5k.kill_reservation();

 def __deploy_iotlab(self):
#  self.iotlab.use_existing_reservation(103514)
  id = self.iotlab.book_nodes();
#  print(id)
  nodes = self.iotlab.get_nodes();

  print(nodes)
  map_nodes = {
   'a8': None,
   'border-router': None,
   'm3': []
  }
  for n in nodes:
   if n.startswith('a8'):
    map_nodes['a8'] = n;
   else:
    if map_nodes['border-router'] is None:
     map_nodes['border-router'] = n
    else:
     map_nodes['m3'].append(n)

  print(map_nodes)

  self.iotlab.wait_nodes();

  self.iotlab.deployenv_m3_border(map_nodes['border-router']);
  self.iotlab.tunnel_frontend_to_a8(map_nodes['a8'])
  self.iotlab.udp2tcp_a8(map_nodes['a8'])
  ipfs_ip = self.iotlab.get_ip_a8(map_nodes['a8'])
  print(ipfs_ip)

  self.iotlab.deployenv_m3(map_nodes['m3'][0]);
  self.iotlab.m3_cmd(map_nodes['m3'][0], 'ping6 2001:910:800::40');

  self.iotlab.m3_cmd(map_nodes['m3'][0], 'ipfs %s get obj1' % (ipfs_ip));

#  self.iotlab.kill_uhcpd()
#  self.iotlab.kill_reservation()
  print('ok')

 def deploy(self):
  g5k_thread = Thread(target=self.__deploy_g5k(), args=());
  iotlab_thread = Thread(target=self.__deploy_iotlab(), args=());

  g5k_thread.start();
  iotlab_thread.start();

  g5k_thread.join();
  iotlab_thread.join();

 def play(self):
  print('play')

 # deploy g5k / install ipfs
 # deploy iotlab flash m3!
 # set ssh tunnel between g5k andn iotlab
 # put an object

