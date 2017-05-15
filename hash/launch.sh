#!/bin/bash

for i in {1..10}; do
 rm /tmp/ids
 ./bench_named.py  write 100 10000000 192.168.10.152 > 100x10M-${i}_write.txt
 ./bench_named.py  read 100 10000000 192.168.10.152 > 100x10M-${i}_read.txt
 read -p 'ok'
done
