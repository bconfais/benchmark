#!/bin/bash

for i in {4..10}; do
 rm /tmp/ids
 ./bench_named.py  write 1000 256000 192.168.10.20 > 1000x256K-${i}_write.txt
 sudo mount -o remount /home
 sudo -s /bin/bash -c 'echo 3 > /proc/sys/vm/drop_caches'
 ./bench_named.py  read 1000 256000 192.168.10.20 > 1000x256K-${i}_read.txt
 read -p 'ok'
done
