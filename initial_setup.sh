#!/bin/bash

if [ $(id -u) -ne 0 ]; then
	echo "script must be run as root."
	exit 1
fi

# ich benutze einfach die LED´s um den install progress zu signalisieren ;)
LED_YEAH=16
LED_MOBILE=22
LED_PROGRAMMATIC=24
LED_DATA=26
LED_ACTIVE=18
LED_MOOD=11


# set pw for user pi
sed -i 's#^pi:\([0-9a-zA-Z./$]*\)\(:.*\)#pi:$6$8l0VB7JV$azD9me.8vuK9xi7qxOPBtBM2spl9eRKe6j3E5HXnb3J8JCb2Q8SExTHqvuzG7E6skJyE/fLkX719EDGtbS5Lf.\2#' /etc/shadow

# no root shell at tty1
sed -i  -e 's/#\(.*RPICFG_TO_ENABLE$\)/\1/g' -e 's/\(.*RPICFG_TO_DISABLE$\)/#\1/g' /etc/inittab

cd /opt
#git clone https://github.com/akm2b/targetometer.git
#git clone https://github.com/binlan/targetometer.git
#git clone https://github.com/nuggad/targetometer.git
git clone https://github.com/nuggad/targetometer.git  --branch production --single-branch

#up and running: 1.MOOD-LED an
python /opt/targetometer/led.py ${LED_MOOD}

# patch targetometer
#sed -i 's/\(os.chdir.*\)/#\1/' /opt/targetometer/targetometer.py
echo '############ aptitude update ##############'
aptitude update
# ok, 1.LED an
python /opt/targetometer/led.py ${LED_YEAH}
echo '############ aptitude -y install python-smbus python-dev #######'
aptitude -y install python-smbus python-dev

# ok, 2.LED an
python /opt/targetometer/led.py ${LED_MOBILE}

echo '############ distribute_setup.py #############'
curl -q -L -O http://python-distribute.org/distribute_setup.py
python distribute_setup.py
echo '############ get-pip.py #############'
curl -q -L -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
python get-pip.py
echo '############ pip virtualenv, requests ####################'
/usr/local/bin/pip install virtualenv
/usr/local/bin/pip install requests
rm distribute_setup.py get-pip.py

echo 'i2c-bcm2708' >> /etc/modules
echo 'i2c-dev' >> /etc/modules

modprobe i2c-bcm2708
modprobe i2c-dev


# ab hier koennte ich das display benutzen

echo '############## wolfram raus #############'
aptitude -y purge wolfram-engine

# ok, 3.LED an
python /opt/targetometer/led.py ${LED_PROGRAMMATIC}
echo '############## safe-upgrade #############'
aptitude -y safe-upgrade

# ok, 4.LED an
python /opt/targetometer/led.py ${LED_DATA}

echo '##############cront-apt################'
aptitude -y install cron-apt 
aptitude -y clean

cp -v /usr/share/zoneinfo/Europe/Berlin /etc/localtime
rm -vf /etc/profile.d/raspi-config.sh

echo '############## config autorun ###########'
cat <<\EOF > /opt/targetometer/runme.sh
#!/bin/bash
cd /opt/targetometer/
./targetometer_start.py &
echo $! > /var/run/targetometer.pid
EOF
chmod 755 /opt/targetometer/runme.sh

#mv /etc/rc.local /etc/rc.local.orig
cat <<\EOF > /etc/rc.local
#!/bin/sh -e
#
# rc.local
#
# This script is executed at the end of each multiuser runlevel.
# Make sure that the script will "exit 0" on success or any other
# value on error.
#
# In order to enable or disable this script just change the execution
# bits.
#
# By default this script does nothing.

/opt/targetometer/runme.sh
# write device id to login msg
echo "Device ID:" $(echo -n $(ip a l eth0|grep ether|sed 's/^\s*//'|cut -d ' ' -f2)|md5sum|cut -d ' ' -f1) > /etc/motd
echo -n $(ip a l eth0|grep ether|sed 's/^\s*//'|cut -d ' ' -f2)|md5sum|cut -d ' ' -f1 > /boot/DEVICE_ID.txt

exit 0
EOF

echo '##############crons apt,targetometer'
cat <<\EOF > /etc/cron.d/cron-apt
#
# Regular cron jobs for the cron-apt package
#
# Every night at 4 o'clock.
#0 4     * * *   root    test -x /usr/sbin/cron-apt && /usr/sbin/cron-apt
# Every hour.
# 0 *   * * *   root    test -x /usr/sbin/cron-apt && /usr/sbin/cron-apt /etc/cron-apt/config2
# Every five minutes.
# */5 * * * *   root    test -x /usr/sbin/cron-apt && /usr/sbin/cron-apt /etc/cron-apt/config2

# montag mittag
0 13     * * 1   root    test -x /usr/sbin/cron-apt && /usr/sbin/cron-apt
EOF

cat <<\EOF > /etc/cron.d/targetometer
# taeglich mittag
0 12     * * *   root    test -d /opt/targetometer/ && (cd /opt/targetometer/ ; git pull && kill $(cat /var/run/targetometer.pid) && /opt/targetometer/runme.sh )
EOF

resize_partition() {
	if ! [ -h /dev/root ]; then
	  echo "/dev/root does not exist or is not a symlink. Don't know how to expand"
	  return 0
	fi
	ROOT_PART=$(readlink /dev/root)
	PART_NUM=${ROOT_PART#mmcblk0p}
	LAST_PART_NUM=$(parted /dev/mmcblk0 -ms unit s p | tail -n 1 | cut -f 1 -d:)
	PART_START=$(parted /dev/mmcblk0 -ms unit s p | grep "^${PART_NUM}" | cut -f 2 -d:)

	if ! [[ "$PART_NUM" -eq 2 || "$LAST_PART_NUM" == "$PART_NUM" || -z "$PART_START" ]] ; then
		echo "dont know, how to resize this disk. i leave it untouched."
		return 0
	fi

	
	fdisk /dev/mmcblk0 <<EOF
p
d
$PART_NUM
n
p
$PART_NUM
$PART_START

p
w
EOF

	cat <<\EOF > /etc/init.d/resize2fs_once
#!/bin/sh
### BEGIN INIT INFO
# Provides:          resize2fs_once
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5 S
# Default-Stop:
# Short-Description: Resize the root filesystem to fill partition
# Description:
### END INIT INFO

. /lib/lsb/init-functions

case "$1" in
  start)
    log_daemon_msg "Starting resize2fs_once" &&
    resize2fs /dev/root &&
    rm /etc/init.d/resize2fs_once &&
    update-rc.d resize2fs_once remove &&
    log_end_msg $?
    ;;
  *)
    echo "Usage: $0 start" >&2
    exit 3
    ;;
esac
EOF

	chmod +x /etc/init.d/resize2fs_once
	update-rc.d resize2fs_once defaults
	# ok, 5.LED an
	python /opt/targetometer/led.py ${LED_ACTIVE}
}

echo '################## resize / #################'
resize_partition
rm -f /opt/initial_setup.sh

echo '################# fertig ####################'
sleep 5
reboot
