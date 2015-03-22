#!/bin/bash
cd /opt/targetometer/
./targetometer_start.py &
echo $! > /var/run/targetometer.pid
