import paramiko
import json
import datetime
import pytz
import math
import re
import time
import sys
from testbed import testbed

class g5k_testbed(testbed):

 def __init__(self, config):
  super(g5k_testbed, self).__init__(config);
  self.config.ssh.via = 'access-north.grid5000.fr';
  self.config.ssh.hostname = self.config.site;


 def kill_reservation(self):
  if self.jobid is None:
   print('No reservation')
   return False
  stdin, stdout, stderr = self._ssh().exec_command(('oardel %d' % (self.jobid)));
  stdout = stdout.read()
  self.jobid = None

 def book_nodes(self):
  if self.jobid is not None:
   print('There is already a reservation')
   return False
  now = pytz.timezone('Europe/Paris').normalize(pytz.timezone('UTC').localize(datetime.datetime.utcnow()).astimezone(pytz.UTC))
  next_slot = (now.hour,  int(5*math.ceil(now.minute/5)) )
  if next_slot[1] == 0:
   next_slot = (next_slot[0]+1, next_slot[1]);

  cmd = ('oarsub  -t deploy -l "{cluster in (\'%s\')}/switch=1/nodes=%d,walltime=%02d:%02d:00" -r "%04d-%02d-%02d %02d:%02d:00"' %
   (self.config.booking.cluster, self.config.booking.nodes, self.config.booking.duration/60, self.config.booking.duration%60, now.year, now.month, now.day, next_slot[0], next_slot[1]))
  stdin, stdout, stderr = self._ssh().exec_command(cmd);
  stdout = stdout.readlines()
  if ['Reservation valid --> OK\n'] != stdout[-1:]:
    print(stdout[-1:])
    return None
  jobid_re = re.compile('^OAR_JOB_ID=([0-9]+)\n')
  for l in stdout:
   jobid_re_ = jobid_re.search(l)
   if jobid_re_:
     jobid = jobid_re_.group(1)
     self.jobid = int(jobid)
     print('Reservation of %d nodes on the %s cluster at %02d:%02d (%d)' % (self.config.booking.nodes, self.config.booking.cluster, next_slot[0], next_slot[1], self.jobid))
     return jobid
  print('OAR_JOB_ID not found')
  return None

 def wait_nodes(self):
  if self.jobid is None:
   print('No reservation')
   return False
  print('Wait node.', end='')
  sys.stdout.flush()
  while True:
   print('.', end='')
   sys.stdout.flush()
   stdin, stdout, stderr = self._ssh().exec_command(("oarstat -sj %d" % (self.jobid)));
   if stdout.read().decode('utf-8').find('Running') != -1:
    print('')
    return True
   time.sleep(3)

 def get_nodes(self):
  stdin, stdout, stderr = self._ssh().exec_command(("oarstat -fJj %d" % (self.jobid)));
  s = json.loads(stdout.read());
  nodes = [f.split('.')[0] for f in s[str(self.jobid)]['assigned_network_address']]
  if 'reserved_resources' in s[str(self.jobid)]:
   nodes += [s[str(self.jobid)]['reserved_resources'][g]['network_address'] for g in s[str(self.jobid)]['reserved_resources'] if 'network_address' in s[str(self.jobid)]['reserved_resources'][g]]
  return nodes;

 def deployenv_nodes(self,nodes):
  if self.jobid is None:
   print('No reservation')
   return False
  if nodes is None:
   nodes = self.get_nodes()

  self._ssh().exec_command("echo -n '' > ~/n")
  for n in nodes:
   self._ssh().exec_command(("echo %s >> ~/n" % (n)))
  print('Deploy %s on %s' % (self.config.env, nodes))
  cmd = ('kadeploy3 -f ~/n -e %s -k' % (self.config.env))
  stdin, stdout, stderr = self._ssh().exec_command(cmd);
  s = stdout.read()

 def install_ipfs(self, node):
  if self.jobid is None:
   print('No reservation')
   return False
  print(('Install IPFS on %s' % (node)))
  self._copy_file(self.config.ipfs.local_service, ('/home/%s/ipfs.service' %(self.config.ssh.username)), self._ssh())
  self._copy_file(self.config.ipfs.local_binary, ('/home/%s/ipfs' % (self.config.ssh.username)), self._ssh())
  self._ssh().exec_command(('scp ~/ipfs root@%s:/tmp/ipfs' % (node)))
  self._ssh().exec_command(('scp ~/ipfs.service root@%s:/etc/systemd/system/ipfs.service' % (node)))

  commands = [
    'mkdir -p "%s"' % (self.config.ipfs.object_dir),
    'mount -t tmpfs tmpfs "%s"' % (self.config.ipfs.object_dir),
    'rm /tmp/config',
    'rm -rf /tmp/datastore',
    'systemctl daemon-reload',
    'IPFS_PATH=%s /tmp/ipfs init' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs config --json Discovery.MDNS.Enabled false' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs config --json Gateway.Writable true' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/8080"' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs config Addresses.API "/ip6/::/tcp/5001"' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs config Datastore.StorageMax "500GB"' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs config Datastore.Path "/tmp/datastore"' % (self.config.ipfs.object_dir),
    'IPFS_PATH=%s /tmp/ipfs bootstrap rm --all' % (self.config.ipfs.object_dir)
   ]
  for c in commands:
   print(c)
   stdin, stdout, stderr = self._ssh_on_node(node, 'root').exec_command(c);
   print(stdout.read())
   print(stderr.read())

 def start_ipfs(self, node):
  if self.jobid is None:
   print('No reservation')
   return False
  stdin, stdout, stderr = self._ssh_on_node(node, 'root').exec_command("systemctl start ipfs");
  stdout.read()

 def tunnel_g5k_to_iotlab(self, node, iotlab_hostname, iotlab_username, iotlab_key, iotlab_password):
  self._copy_file(iotlab_key, ('/home/%s/iotlab_key' %(self.config.ssh.username)), self._ssh())
  self._copy_file(("%s.pub" % (iotlab_key)), ('/home/%s/iotlab_key.pub' %(self.config.ssh.username)), self._ssh())
  self._copy_file(self.config.tunnel_script, ('/home/%s/tunnel.sh' %(self.config.ssh.username)), self._ssh())
  cmd = "chmod 755 /home/%s/tunnel.sh" % (self.config.ssh.username)
  stdin, stdout, stderr = self._ssh().exec_command(cmd);
  iotlab_password = iotlab_password.replace('#', '\#')
  cmd = "/home/%s/tunnel.sh %s -o StrictHostKeyChecking=no -i '/home/%s/iotlab_key' -TfN -R 5001:[::1]:5001 %s@%s" % (self.config.ssh.username, iotlab_password, self.config.ssh.username, iotlab_username, iotlab_hostname)
  print("Establish tunnel between G5k node %s and the frontend iotlab" % (node))
  stdin, stdout, stderr = self._ssh_on_node(node, 'root').exec_command(cmd);
