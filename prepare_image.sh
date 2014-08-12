#!/bin/bash

if ! [ -f raspbian.img ] ; then 
	if ! [ -f raspbian.img.zip ] ; then 
		echo "### download raspbian"
		curl -L -q http://downloads.raspberrypi.org/raspbian_latest > raspbian.img.zip
	fi
	echo "### unpack raspbian archive"
	unzip -x raspbian.img.zip
	mv $(ls -1 *raspbian.img) raspbian.img
fi
sudo which kpartx > /dev/null || { 
	echo "### install kpartx"
	sudo aptitude -y install kpartx 
}
echo "### loop mount raspbian linux partition"
MP=$(sudo mktemp -d --tmpdir=/media)
DEVICE=$(sudo kpartx -a -v raspbian.img|tail -n 1|cut -d' ' -f3)
sleep 3
sudo mount /dev/mapper/${DEVICE} ${MP}
if mountpoint -q ${MP}  ; then
	echo "### copy our install files to raspian."
	sudo cp -v ./initial_setup.sh ${MP}/opt/
	sudo chmod 755 ${MP}/opt/initial_setup.sh
	#sudo ls -l ${MP}/opt/
	if ! [[ -f ${MP}/etc/rc.local.orig ]] ; then 
		sudo mv -v ${MP}/etc/rc.local ${MP}/etc/rc.local.orig
	fi
	cat <<\EOF > rc.local
#!/bin/sh -e

/opt/initial_setup.sh 2>&1 > /opt/targetometer_install.log &

exit 0
EOF
	sudo mv -v rc.local ${MP}/etc/rc.local
	sudo chmod 755 ${MP}/etc/rc.local
	echo "### cleanup"
	sudo umount ${MP}
	sudo rm -rf ${MP}
	sudo kpartx -d raspbian.img > /dev/null
	echo "### ready."
	echo "### dd image to sd card and boot it in a targetometer"
	echo "### eg. >>>> sudo dd if=raspbian.img of=/dev/sdb bs=10MB <<<< or"
	echo "### eg. >>>> dd if=raspbian.img bs=10MB | pv -s 3G | sudo dd of=/dev/sdb bs=10MB <<<<"
else
	echo "### something goes wrong"
	sudo umount ${MP}
	sudo rm -rf ${MP}
	sudo kpartx -d raspbian.img > /dev/null
fi

