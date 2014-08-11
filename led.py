import sys
import RPi.GPIO as GPIO

led = int(sys.argv[1])
GPIO.setmode(GPIO.BOARD)
GPIO.setup(led, GPIO.OUT)
GPIO.output(led,True)
