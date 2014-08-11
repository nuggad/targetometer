targetometer
============

```
./prepare_image.sh
```
- put a SD Card in
```
dd if=raspbian.img bs=10MB | pv -s 3G | sudo dd of=/dev/sdb bs=10MB
```
- put the SD Card in a targetometer (with ethernet connection to internet)
- boot it and wait ~20 min
- if everything went through, targetometer will come up with working display and so on.
