#!/bin/bash

PS=11
KEY=9

# init
echo ${KEY} > /sys/class/gpio/export
echo ${PS}  > /sys/class/gpio/export
echo "out"  > /sys/class/gpio/gpio${KEY}/direction
echo "in"   > /sys/class/gpio/gpio${PS}/direction


pushKeyButton () {
        echo "1" > /sys/class/gpio/gpio${KEY}/value
        sleep 2
        echo "0" > /sys/class/gpio/gpio${KEY}/value
}

status () {
        cat /sys/class/gpio/gpio${PS}/value
}

# check if fona is on or off 1=on 0=off
if [ $(status) -eq 1 ] ; then
        # turn it off and on again
        pushKeyButton
        sleep 3
        pushKeyButton
else
        pushKeyButton
fi

sleep 3
if [ $(status) -eq 1 ] ; then
        ifup fona
else
        # maybe no fona there?
        echo "no fona, do nothing"
fi

# cleanup
echo ${KEY} > /sys/class/gpio/unexport
echo ${PS}  > /sys/class/gpio/unexport
