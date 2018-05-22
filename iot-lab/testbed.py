import paramiko
import socket
import subprocess
import os
from contextlib import closing
from abc import ABCMeta, abstractmethod
from utils import dotdict

class testbed(object, metaclass=ABCMeta):

 @abstractmethod
 def __init__(self, config):
  self.config = config
  self.jobid = None
  self.__ssh = dotdict()
  self.__ssh_key = paramiko.RSAKey.from_private_key_file(self.config.ssh.key, password=self.config.ssh.password);

 def __del__(self):
  for node in self.__ssh:
    if node not in ['frontend', 'via']:
     print(("disconnect from %s..." % node), end='')
     self.__ssh[node].close()
     print("ok")
  if 'frontend' in self.__ssh:
   print("disconnect from site frontend...", end='')
   self.__ssh.frontend.close()
   print("ok")
  if 'via' in self.__ssh:
   print("disconnect from general frontend...", end='')
   self.__ssh.via.close()
   print("ok")

 def _find_free_port(self):
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
   s.bind(('localhost', 0))
   return s.getsockname()[1]

 def _ssh(self):
  """establish an ssh connection to the site frontend"""
  if 'frontend' not in self.__ssh:
   if self.config.ssh.via is None:
    self.__ssh.frontend = paramiko.SSHClient();
    self.__ssh.frontend.set_missing_host_key_policy(paramiko.AutoAddPolicy());
    print("direct connection");
    print("connection to site frontend...", end='');
    self.__ssh.frontend.connect(hostname=self.config.ssh.hostname, username=self.config.ssh.username, pkey=self.__ssh_key);
    print("ok");
   else:
    self.__ssh.via = paramiko.SSHClient();
    self.__ssh.via.set_missing_host_key_policy(paramiko.AutoAddPolicy());
    print("tunneled connection")
    print("connecting to general frontend...", end='');
    self.__ssh.via.connect(hostname=self.config.ssh.via, username=self.config.ssh.username, pkey=self.__ssh_key);
    print("ok");
    transport = self.__ssh.via.get_transport()
    port = self._find_free_port()
    channel = transport.open_channel('direct-tcpip', (self.config.ssh.hostname, 22), ('127.0.0.1', port))

    self.__ssh.frontend = paramiko.SSHClient();
    self.__ssh.frontend.set_missing_host_key_policy(paramiko.AutoAddPolicy());
    print("connecting to site frontend...", end='');
    self.__ssh.frontend.connect(hostname='127.0.0.1', port=port, username=self.config.ssh.username, pkey=self.__ssh_key, sock=channel);
    print("ok");

  return self.__ssh.frontend

 def _ssh_on_node(self, node, username=None):
  """establish an ssh connection to a node inside the site (the ssh connection is tunnelled through the site frontend)"""
  if username is None:
   username = self.config.ssh.username
  if node not in self.__ssh:
   transport = self._ssh().get_transport()
   port = self._find_free_port()
   channel = transport.open_channel('direct-tcpip', (node, 22), ('127.0.0.1', port))
   self.__ssh[node] = paramiko.SSHClient();
   self.__ssh[node].set_missing_host_key_policy(paramiko.AutoAddPolicy());
   print(("connecting to node %s..." % node), end='');
   self.__ssh[node].connect(hostname='127.0.0.1', port=port, username=username, pkey=self.__ssh_key, sock=channel);
   print("ok");
  return self.__ssh[node]

 def _copy_file(self, local_file, remote_file, ssh_connection):
  """copy the local file on a remote node only if the file on the remote node does not exist or is different"""
  cp = False
  stdin, stdout, stderr = ssh_connection.exec_command(('sha1sum %s' % (remote_file)));
  if len(stderr.read()) != 0:
   cp = True
  if os.path.exists(local_file) and os.path.isfile(local_file):
   remote_sha = stdout.read().decode('utf-8').split('  ')[0]
   local_sha = subprocess.check_output(['sha1sum', local_file]).decode('utf-8').split('  ')[0]
   if remote_sha != local_sha:
    cp = True
  if cp:
   print('File %s missing, copy it' % (remote_file))
   sftp = ssh_connection.open_sftp()
   sftp.put(local_file, remote_file)


 @abstractmethod
 def book_nodes(self):
  """make a nodes reservation"""
  pass

 @abstractmethod
 def wait_nodes(self):
  """wait until the reservation is launched and running"""
  pass

 @abstractmethod
 def get_nodes(self):
  """get list of the reserved nodes"""
  pass

 def use_existing_reservation(self, jobid):
  """mainly to test, connect to an existing reservation instead of booking nodes"""
  self.jobid = int(jobid)
  pass

 @abstractmethod
 def kill_reservation(self):
  """terminate the current reservation"""
  pass

 def get_ssh_params(self):
  """return params of the ssh connection in order to establish the tunnel between the platforms"""
  return (self.config.ssh.hostname, self.config.ssh.username, self.config.ssh.key, self.config.ssh.password)
