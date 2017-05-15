#!/bin/bash

for i in {1..10}; do
 rm /tmp/ids
 ./bench_named.py  write 100 256000 192.168.10.153 > 100x256K-${i}_write.txt
 ./bench_named.py  read 100 256000 192.168.10.153 > 100x256K-${i}_write.txt
done
