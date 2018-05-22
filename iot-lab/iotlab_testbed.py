import paramiko
import json
import ipaddress
import math
import time
import sys
import socket
from utils import dotdict
from testbed import testbed

class iotlab_testbed(testbed):

 def __init__(self, config):
  super(iotlab_testbed, self).__init__(config);
  self.config.ssh.hostname = self.__fqdn(None)
  self.config.ssh.via = None
  self.__m3_ip = dotdict()

 def __ipv6_prefix(self,node, i):
  pprefix = None
  if 'grenoble' == self.config.site:
   pprefix = ipaddress.IPv6Address('2001:660:5307:3100::')
  elif 'lille' == self.config.site:
   pprefix = ipaddress.IPv6Address('2001:660:4403:0480::')
  elif 'saclay' == self.config.site:
   pprefix = ipaddress.IPv6Address('2001:660:3207:04c0::')
  elif 'strasbourg' == self.config.site:
   pprefix = ipaddress.IPv6Address('2001:660:4701:f0a0::')

  nodeid = int(str(node).split('.')[0].split('-')[1])*math.pow(16, 16)
  nodeid += i*math.pow(16, 16)
  prefix = pprefix + int(nodeid)
  return "%s/64" % (prefix)

 def __fqdn(self, node):
  if node is None:
   return "%s.iot-lab.info" % (self.config.site)
  else:
   return "%s.%s.iot-lab.info" % (node, self.config.site)

 def kill_reservation(self):
  if self.jobid is None:
   print('No reservation')
   return False
  stdin, stdout, stderr = self._ssh().exec_command(('experiment-cli stop -i %d' % (self.jobid)));
  s = json.loads(stdout.read());
  print(s)
  self.jobid = None

 def book_nodes(self):
  if self.jobid is not None:
   print('There is already a reservation')
   return False
  cmd = ('experiment-cli submit -d %d -l %d,archi=a8:at86rf231+site=%s -l %d,archi=m3:at86rf231+site=%s' %
   (self.config.booking.duration, self.config.booking.a8, self.config.site, self.config.booking.m3, self.config.site))
  stdin, stdout, stderr = self._ssh().exec_command(cmd);
  s = stdout.read()
  s = json.loads(s)
  self.jobid = int(s['id'])
  print('Reservation of %d a8-nodes and %d-m3 nodes (%d)' % (self.config.booking.a8, self.config.booking.m3, self.jobid))
  time.sleep(20)
  return int(s['id'])

 def wait_nodes(self):
  if self.jobid is None:
   print('No reservation')
   return False
  print('Wait node.', end='')
  sys.stdout.flush()
  while True:
   print('.', end='')
   sys.stdout.flush()
   stdin, stdout, stderr = self._ssh().exec_command(("experiment-cli get -i %d -s" % (self.jobid)));
   s = stdout.read()
   s = json.loads(s)
   if s['state'] == 'Running':
    print('')
    return True
   time.sleep(3)

 def get_nodes(self):
  stdin, stdout, stderr = self._ssh().exec_command(("experiment-cli get -i %d -r" % self.jobid));
  s = json.loads(stdout.read());
  return [f['network_address'].split('.')[0] for f in s['items']];

 def __deployenv(self, local_env, remote_env, node):
  self._copy_file(local_env, remote_env, self._ssh())
  stdin, stdout, stderr = self._ssh().exec_command('node-cli --update "%s" -l %s,%s' % (remote_env, self.config.site, node.replace('-', ',')) )
  s = stdout.read()
  s = json.loads(s)
  return s

 def deployenv_m3_border(self, node):
  if self.jobid is None:
   print('No reservation')
   return False
  self.__deployenv(self.config.env.border_router, ('/senslab/users/%s/gnrc_border_router.elf' % (self.config.ssh.username)), node)
  prefix = self.__ipv6_prefix(node, 0)
  print(prefix)
  cmd = "sudo /opt/ethos_tools/ethos_uhcpd.py \"%s\" tap0 %s &" % (node, prefix)
  print(cmd)
  stdin, stdout, stderr = self._ssh().exec_command(cmd)

 def deployenv_m3(self, node):
  if self.jobid is None:
   print('No reservation')
   return False
  self.__deployenv(self.config.env.node, ('/senslab/users/%s/node.elf' % (self.config.ssh.username)), node)
  sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
  server_address = ('::', 1234)
  sock.bind(server_address)
  data, address = sock.recvfrom(4096)
  self.__m3_ip[node] = address[0]
  sock.close()

 def tunnel_frontend_to_a8(self, a8_node):
  if self.jobid is None:
   print('No reservation')
   return False
  cmd = ('ssh -fN -R :5001:[::]:5001 root@node-%s' % (self.__fqdn(a8_node)))
  stdin, stdout, stderr = self._ssh().exec_command(cmd)

 def get_ip_a8(self, a8_node):
  if self.jobid is None:
   print('No reservation')
   return False
  cmd = 'ifconfig | grep inet6 | grep Scope:Global | awk \'{print $3}\' | awk -F % \'{print $1}\''
  stdin, stdout, stderr = self._ssh_on_node("node-%s" % (self.__fqdn(a8_node)), 'root').exec_command(cmd)
  return stdout.read().decode('utf-8').replace('\n', '')

 def udp2tcp_a8(self, a8_node):
  self._copy_file(self.config.udp2tcp, ('/senslab/users/%s/udp2tcp' % (self.config.ssh.username)), self._ssh())
  self._ssh().exec_command('scp /senslab/users/%s/udp2tcp root root@node-%s:~/udp2tcp' % (self.config.ssh.username, self.__fqdn(a8_node)))
  cmd = '~/udp2tcp 5001'
  self._ssh().exec_command(cmd);

 def m3_cmd(self, m3_node, cmd):
  if self.jobid is None:
   print('No reservation')
   return False;
  if m3_node not in  self.__m3_ip:
   print('No known ip address for this node')
   return False;
  sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) # UDP
  sock.sendto(bytes("%s\n" % (cmd), "utf-8"), (self.__m3_ip[m3_node], 1234))
  d = sock.recvfrom(256)
  sock.close()
  return d[0].decode('utf-8')

 def kill_uhcpd(self):
  if self.jobid is None:
   print('No reservation')
   return False
  stdin, stdout, stderr = self._ssh().exec_command(("ps aux | grep \"^%s\" | grep uhcpd | grep -v grep | awk '{print $2}'" % (self.config.ssh.username) ));
  uhcpd = stdout.read().decode('utf-8').replace('\n', ' ')
  stdin, stdout, stderr = self._ssh().exec_command(("ps aux | grep \"^%s\" | grep ssh | grep a8 | grep -v grep | awk '{print $2}'" % (self.config.ssh.username) ));
  ssh = stdout.read().decode('utf-8').replace('\n', ' ')
  stdin, stdout, stderr = self._ssh().exec_command(("kill %s %s" % (uhcpd, ssh) ));
  print(stdout.read())



