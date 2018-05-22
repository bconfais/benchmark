#!/usr/bin/python
import sys
import getpass
from iotlab_testbed import iotlab_testbed
from g5k_testbed import g5k_testbed
from scenario import scenario
from utils import dotdict

config = dotdict({
 'iotlab': {
  'site': 'grenoble',
  'env': {
   'border_router': "files/gnrc_border_router.elf",
   'node': "files/test-iotlab.elf"
  },
  'udp2tcp': 'file/tcp2udp',
  'booking': {
   'duration': 60,
   'm3': 2,
   'a8': 1
  },
  'ssh': {
   'username': 'confais',
   'key': '/home/bastien/.ssh/id_rsa_grid5k'
  }
 },
 'g5k': {
  'site': 'grenoble',
  'booking': {
   'duration': 60,
   'cluster': 'edel',
   'nodes': 1
  },
  'env': "jessie-x64-nfs",
  'ipfs': {
   'local_binary': "files/ipfs", #in the current directory
   'local_service': "files/ipfs.service",
   'object_dir': '/mnt/ipfs'
  },
  'tunnel_script': "files/tunnel.sh",
  'ssh': {
   'username': 'bconfais',
   'key': '/home/bastien/.ssh/id_rsa_grid5k'
  }
 }
})

if '__main__' == __name__:
 pw = getpass.getpass()
 config['iotlab']['ssh']['password'] = pw
 config['g5k']['ssh']['password'] = pw

 iotlab = iotlab_testbed(config.iotlab)
 g5k = g5k_testbed(config.g5k)

 sc = scenario(g5k, iotlab)
 sc.deploy()
 sc.play()

 # book nodes (2 nodes m3 and 1 a8 on iotlab)
# g5k.book_nodes()
# g5k.wait_nodes()
# iotlab.deploy('')


 # deploy g5k / install ipfs
 # deploy iotlab flash m3!
 # set ssh tunnel between g5k andn iotlab
 # put an object
 # read it

# print(iotlab.get_nodes())
# print(g5k.get_nodes())
 sys.exit(0);
