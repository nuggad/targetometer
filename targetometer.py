#!/usr/bin/python

from time import sleep, strftime, localtime
from threading import Timer
from Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
import RPi.GPIO as GPIO
import fcntl, socket, struct
import requests
import os
import time
import datetime
import subprocess
import thread
import hashlib

class Targetometer:

  #constants
  LED_YEAH = 16
  LED_MOBILE = 22
  LED_PROGRAMMATIC = 24
  LED_DATA = 26
  LED_ACTIVE = 18
  logo_1_1 = [0b00000,0b00000,0b00000,0b00000,0b00000,0b00000,0b00000,0b00111]
  logo_1_2 = [0b00000,0b00111,0b01111,0b01111,0b01111,0b01111,0b11000,0b10000]
  logo_1_3 = [0b00000,0b00000,0b10000,0b10000,0b10000,0b10000,0b11111,0b01111]
  logo_1_4 = [0b00000,0b00000,0b00000,0b00000,0b00000,0b00000,0b10000,0b11000]
  logo_2_1 = [0b01111,0b11111,0b11111,0b11110,0b01100,0b00000,0b00000,0b00000]
  logo_2_2 = [0b00000,0b00000,0b00000,0b00000,0b00000,0b00000,0b00000,0b00000]
  logo_2_3 = [0b01111,0b01111,0b00111,0b00000,0b00000,0b00000,0b00000,0b00000]
  logo_2_4 = [0b11000,0b10000,0b00000,0b00000,0b00000,0b00000,0b00000,0b00000]
  
  #hardware and status
  lcd = Adafruit_CharLCDPlate()
  version = None
  device_id = "SOME_DEVICE_ID"
  connectionOK = False
  blockLCD = False
  firstUpdate = True
  yeah_led = False
  
  #data
  data = None
  data_time = None
  
  def __init__(self):
    #os.chdir("/home/pi/2b")
    os.chdir(os.path.dirname(__file__))
    print subprocess.check_output(["pwd"])
    self.version = subprocess.check_output(["git" , "describe"])
    
    t = self
    m = hashlib.md5()
    m.update(self.get_hw_addr('eth0'))
    #self.device_id =  m.hexdigest()
    print "deviceid: " + m.hexdigest()
    print self.version
    self.gpio_setup()
    self.initialize_targetometer()
    self.query_customer_kpis()
    if self.connectionOK == True:
      self.register_button()
      self.show_customer_kpis()

  def initialize_targetometer(self):
    self.lcd.clear()
    self.lcd.createChar(1, self.logo_1_1)
    self.lcd.createChar(2, self.logo_1_2)
    self.lcd.createChar(3, self.logo_1_3)
    self.lcd.createChar(4, self.logo_1_4)
    self.lcd.createChar(5, self.logo_2_1)
    self.lcd.createChar(6, self.logo_2_2)
    self.lcd.createChar(7, self.logo_2_3)
    self.lcd.createChar(8, self.logo_2_4)
    self.lcd.begin(1,1)
    self.lcd.message("  " + chr(1)+chr(2)+chr(3)+chr(4) + "\n")
    self.lcd.message("  " + chr(5)+chr(6)+chr(7)+chr(8) + "nugg.ad")
    sleep(3)
    self.lcd.clear()
    thread.start_new_thread(self.blink_all_leds_like_kitt, (1,))
    self.lcd.message("Targetometer\ninitializing...")
    sleep(2)
    self.lcd.clear()
      
  def query_customer_kpis(self):
    self.blockLCD = True
    thread.start_new_thread(self.blink_active_led, (10,)) if self.firstUpdate == True else 1
    self.lcd.clear()
    self.lcd.message("Updating Data...") 
    try:
      self.perform_request()
      self.lcd.message("Updating Data... \nSuccess")
      sleep(1)
      self.connectionOK = True
      update_timer = Timer(3600, self.query_customer_kpis)
      update_timer.start()
      self.firstUpdate = False
      self.evaluate_yeah()
    except requests.exceptions.RequestException as e:
      self.lcd.message("Updating Data... \nConnection Error")
      print str(e)
      self.connectionOK = False
    self.lcd.clear()
    self.blockLCD = False

  def perform_request(self):
    headers = {'targetometer_version' : self.version}
    r = requests.get('https://apistage.nugg.ad/info?device=' + self.device_id, headers= headers, verify=False)
    self.data = r.json()
    self.data_time = datetime.datetime.now()
    #debug
    #print self.data
    #print headers

  def evaluate_yeah(self):
    print self.data['yeah']
    if self.data['yeah'] != None:
      last_yeah = datetime.datetime.strptime(self.data['yeah'], '%Y-%m-%d %H:%M:%S')
      yeah_diff = datetime.datetime.now() - last_yeah
      if yeah_diff.seconds < 3600:
        yeah_led = True
      else:
        yeah_led = False
    
  def update_request_leds(self):
    GPIO.output(self.LED_ACTIVE, True)
    GPIO.output(self.LED_MOBILE, self.data['mobile_requests_ok'])
    GPIO.output(self.LED_PROGRAMMATIC, self.data['programmatic_requests_ok'])
    GPIO.output(self.LED_DATA, self.data['data_requests_ok'])
    GPIO.output(self.LED_YEAH, self.yeah_led)
    
  def show_customer_kpis(self):
    kpis = 10
    duration = 3
    clock_duration = 300 - (kpis * duration)
    
    #update leds
    self.update_request_leds()
    
    #message and user
    self.lcd.message(self.data['message'] + "\n" + self.data['user']) if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1
    
    #last_record - needs better header/description 
    live = datetime.datetime.strptime(self.data['timestamps']['live'], '%Y-%m-%d %H:%M:%S')
    last = datetime.datetime.strptime(self.data['timestamps']['last_record'], '%Y-%m-%d %H:%M:%S')
    server_diff = live-last
    local_diff = datetime.datetime.now() - self.data_time
    diff = server_diff + local_diff
    self.lcd.message("data mined: \n" + str(diff.seconds/60) + "min ago") if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #active flights
    self.lcd.message("active flights: \n" + str(self.data['flights']['active']) + " (" + str(self.data['flights']['active_change']) + ")") if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #daily impressions
    self.lcd.message("daily impressions: \n" + str(self.data['flights']['daily_impressions']) + " (" + str(self.data['flights']['daily_impressions_change']) + ")") if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #hourly impressions
    self.lcd.message("hourly impressions: \n" + str(self.data['flights']['hourly_impressions']) + " (" + str(self.data['flights']['hourly_impressions_change']) + ")") if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #surveys
    #if self.data['surveys']['count'] > 0:
    self.lcd.message("surveys: \n" + str(self.data['surveys']['count']) + " (" + str(self.data['surveys']['count_change']) + ")") if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #best_uplift
    self.lcd.message("best uplift: \n" + "targeting: " + str(self.data['best_uplift']['targeting'])) if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    self.lcd.message("best uplift: \n" + "branding: " + str(self.data['best_uplift']['branding'])) if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #avg_response_time
    self.lcd.message("avg response time: \n" + str(self.data['avg_response_time'])) if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #trending
    self.lcd.message("updates per hour: \n" + str(self.data['trending']['updates_per_hour'])) if self.blockLCD == False else 1
    sleep(duration)
    self.lcd.clear() if self.blockLCD == False else 1

    #date and time loop
    t = 0
    while(t < clock_duration):
      self.lcd.message(strftime("%a, %d %b %Y \n %H:%M:%S           ", localtime())) if self.blockLCD == False else 1
      sleep(1)
      t = t+1
  
    self.lcd.clear()
    self.show_customer_kpis() 
    
  def register_button(self):
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(15, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(15, GPIO.RISING, callback=self.buttonCallback, bouncetime=1000)

  def buttonCallback(self, GPIO):
    print time.time()
    thread.start_new_thread(self.blink_yeah_led, (20,))
    self.blockLCD = True
    self.lcd.clear()
    try:
      headers = {'targetometer_version' : self.version}
      r = requests.post("https://apistage.nugg.ad/targetometer/yeah/?device=" + self.device_id, headers = headers, verify=False)
      if r.status_code == requests.codes.ok:
        self.lcd.me_codessage("Yeah!!!!")
      else:
        r.raise_for_status()
      sleep(3)
      self.lcd.clear()
      print r.status_code
    except requests.exceptions.RequestException as e:
      self.lcd.message("Connection\nProblem " +str(r.status_code))
      sleep(3)
      self.lcd.clear()
    self.blockLCD = False

  #http://stackoverflow.com/questions/159137/getting-mac-address
  def get_hw_addr(self, ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
    return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]

  def gpio_setup(self):
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(self.LED_YEAH, GPIO.OUT)
    GPIO.setup(self.LED_ACTIVE, GPIO.OUT)
    GPIO.setup(self.LED_MOBILE, GPIO.OUT)
    GPIO.setup(self.LED_PROGRAMMATIC, GPIO.OUT)
    GPIO.setup(self.LED_DATA, GPIO.OUT)

    GPIO.output(self.LED_YEAH, False)
    GPIO.output(self.LED_ACTIVE, False)
    GPIO.output(self.LED_MOBILE, False)
    GPIO.output(self.LED_PROGRAMMATIC, False)
    GPIO.output(self.LED_DATA, False)

  def blink_active_led(self, repetitions):
    count = 1
    while count <= repetitions:
      GPIO.output(self.LED_ACTIVE, True)
      sleep(0.05)
      GPIO.output(self.LED_ACTIVE, False)
      sleep(0.05)
      count = count + 1
    GPIO.output(self.LED_ACTIVE, True)

  def blink_yeah_led(self, repetitions):
    count = 1
    while count <= repetitions:
      GPIO.output(self.LED_YEAH, True)
      sleep(0.05)
      GPIO.output(self.LED_YEAH, False)
      sleep(0.05)
      count = count + 1
    #GPIO.output(self.LED_YEAH, self.data['yeah'])


  def blink_all_leds_like_kitt(self, repetitions):
    count = 1
    while count <= repetitions:
      GPIO.output(self.LED_YEAH, True)
      sleep(0.05)
      GPIO.output(self.LED_YEAH, False)
      sleep(0.05)
      GPIO.output(self.LED_MOBILE, True)
      sleep(0.05)
      GPIO.output(self.LED_MOBILE, False)
      sleep(0.05)
      GPIO.output(self.LED_PROGRAMMATIC, True)
      sleep(0.05)
      GPIO.output(self.LED_PROGRAMMATIC, False)
      sleep(0.05)
      GPIO.output(self.LED_DATA, True)
      sleep(0.05)
      GPIO.output(self.LED_DATA, False)
      sleep(0.05)
      GPIO.output(self.LED_ACTIVE, True)
      sleep(0.05)
      GPIO.output(self.LED_ACTIVE, False)
      sleep(0.05)
      GPIO.output(self.LED_DATA, True)
      sleep(0.05)
      GPIO.output(self.LED_DATA, False)
      sleep(0.05)
      GPIO.output(self.LED_PROGRAMMATIC, True)
      sleep(0.05)
      GPIO.output(self.LED_PROGRAMMATIC, False)
      sleep(0.05)
      GPIO.output(self.LED_MOBILE, True)
      sleep(0.05)
      GPIO.output(self.LED_MOBILE, False)
      sleep(0.05)    
      if count == repetitions:
        GPIO.output(self.LED_YEAH, True)
        sleep(0.05)
        GPIO.output(self.LED_YEAH, False)
        sleep(0.05)
      count = count + 1
