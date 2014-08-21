#!/usr/bin/python

from time import sleep, strftime, localtime
from threading import Timer
from threading import Thread
from threading import Event
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
  LED_MOOD = 11
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
  dataOK = False
  firstUpdate = True
  yeah_led = False

  heartbeat_thread = None
  heartbeat_stop_event = None
  idle_thread = None
  idle_stop_event = None
  display_thread = None
  display_stop_event = None
  
  #data
  data = None
  data_time = None
  
  def __init__(self):
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
    if self.connectionOK == True:
      self.query_customer_kpis()
      if self.dataOK == True:
        self.register_button()
        self.start_working()
    
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
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
      s.connect(('google.com', 0))
      self.lcd.message('IP address: \n' + s.getsockname()[0])
      sleep(2)
      self.lcd.clear()
      self.connectionOK = True
    except socket.error as e:
      self.lcd.message('no connection \n to internet')  
      sleep(3)
      self.lcd.clear()
      self.lcd.message('error no.' + str(e.errno))        
      sleep(3)
      self.lcd.clear()
      self.connectionOK = False
    
  def query_customer_kpis(self):
    thread.start_new_thread(self.blink_active_led, (10,)) if self.firstUpdate == True else 1
    self.lcd.clear()
    self.lcd.message("Updating Data...") 
    self.perform_request()
    
  def perform_request(self):
    try:
      headers = {'targetometer_version' : self.version}
      r = requests.get('https://apistage.nugg.ad/info?device=' + self.device_id, headers= headers, verify=False)
      if r.status_code != requests.codes.ok:
        r.raise_for_status()
      self.data = r.json()
      self.data_time = datetime.datetime.now()
      self.lcd.message("Updating Data... \nSuccess")
      sleep(1)
      self.dataOK = True
      update_timer = Timer(3600, self.query_customer_kpis)
      update_timer.start()
      self.firstUpdate = False
      self.evaluate_yeah()
    except requests.exceptions.HTTPError:
      self.lcd.clear()
      self.lcd.message("invalid HTTP\nresponse "  + str(r.status_code))
      sleep(3)
      self.dataOK = False
    except requests.exceptions.Timeout:
      self.lcd.clear()
      self.lcd.message("connection\ntimeout")
      sleep(3)
      self.dataOK = False
    except requests.TooManyRedirects:
      self.lcd.clear()
      self.lcd.message("too many\nredirects")
      sleep(3)
      self.dataOK = False
    except requests.exceptions.RequestException as e:
      self.lcd.clear()
      self.lcd.message("request \nexception")
      sleep(3)
      print str(e)
      self.dataOK = False
    self.lcd.clear()
    
  def evaluate_yeah(self):
    if self.data['yeah'] != None:
      last_yeah = datetime.datetime.strptime(self.data['yeah'], '%Y-%m-%d %H:%M:%S')
      yeah_diff = datetime.datetime.utcnow() - last_yeah
      if yeah_diff.seconds < 86400:
        yeah_led = True
      else:
        yeah_led = False
    
  def update_request_leds(self):
    GPIO.output(self.LED_ACTIVE, True)
    GPIO.output(self.LED_MOBILE, self.data['mobile_requests_ok'])
    GPIO.output(self.LED_PROGRAMMATIC, self.data['programmatic_requests_ok'])
    GPIO.output(self.LED_DATA, self.data['data_requests_ok'])
    GPIO.output(self.LED_YEAH, self.yeah_led)

  def disable_request_leds(self):
    GPIO.output(self.LED_ACTIVE, False)
    GPIO.output(self.LED_MOBILE, False)
    GPIO.output(self.LED_PROGRAMMATIC, False)
    GPIO.output(self.LED_DATA, False)
    GPIO.output(self.LED_YEAH, False)

  def start_idling(self):
    self.heartbeat_stop_event.set()
    self.idle_stop_event = Event()
    self.idle_thread = Thread(target=self.idle, args=(self.idle_stop_event,))
    self.idle_thread.start()

  def start_working(self):
    if self.idle_stop_event != None:
      self.idle_stop_event.set()
    self.display_stop_event = Event()
    self.display_thread = Thread(target=self.show_customer_kpis, args=(self.display_stop_event,))
    self.display_thread.start()
    self.heartbeat_stop_event = Event()
    self.heartbeat_thread = Thread(target=self.heartbeat, args=(self.heartbeat_stop_event,))
    self.heartbeat_thread.start()

  def stop_all_threads(self):
    if self.idle_stop_event != None:
      self.idle_stop_event.set()
    if self.heartbeat_stop_event != None:
      self.heartbeat_stop_event.set()
    if self.display_stop_event != None:
      self.display_stop_event.set()
      
  def show_customer_kpis(self, stop_event):
    duration = 3
    #update leds
    self.update_request_leds()

    if stop_event.is_set():
      return
    
    #message and user
    self.lcd.message(self.data['message'] + "\n" + self.data['user'])
    stop_event.wait(duration)
    self.lcd.clear()
    
    if stop_event.is_set():
      return
    
    #last_record - needs better header/description 
    live = datetime.datetime.strptime(self.data['timestamps']['live'], '%Y-%m-%d %H:%M:%S')
    last = datetime.datetime.strptime(self.data['timestamps']['last_record'], '%Y-%m-%d %H:%M:%S')
    server_diff = live-last
    local_diff = datetime.datetime.now() - self.data_time
    diff = server_diff + local_diff
    self.lcd.message("data mined: \n" + str(diff.seconds/60) + "min ago")
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return
    
    #active flights
    self.lcd.message("active flights: \n" + str(self.data['flights']['active']) + " (" + str(self.data['flights']['active_change']) + ")")
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return

    #daily impressions
    self.lcd.message("daily impressions: \n" + str(self.data['flights']['daily_impressions']) + " (" + str(self.data['flights']['daily_impressions_change']) + ")")
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return
    
    #hourly impressions
    self.lcd.message("hourly impressions: \n" + str(self.data['flights']['hourly_impressions']) + " (" + str(self.data['flights']['hourly_impressions_change']) + ")")
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return

    #survey
    #if self.data['surveys']['count'] > 0:
    self.lcd.message("surveys: \n" + str(self.data['surveys']['count']) + " (" + str(self.data['surveys']['count_change']) + ")")
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return
    
    #best_uplift
    self.lcd.message("best uplift: \n" + "targeting: " + str(self.data['best_uplift']['targeting']))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return

    self.lcd.message("best uplift: \n" + "branding: " + str(self.data['best_uplift']['branding']))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return

    #avg_response_time
    self.lcd.message("avg response time: \n" + str(self.data['avg_response_time']))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return

    #trending
    self.lcd.message("updates per hour: \n" + str(self.data['trending']['updates_per_hour']))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      return
    #disable leds before going to sleep
    self.disable_request_leds()
    self.lcd.clear()

    if not stop_event.is_set():
      self.start_idling()

  def idle(self, stop_event):
    clock_duration = 300
    #date and time loop
    t = 0
    while(t < clock_duration and not stop_event.is_set()):
      self.lcd.message(strftime("%a, %d %b %Y \n %H:%M:%S           ", localtime()))
      stop_event.wait(1)
      t = t+1
    self.lcd.clear()
    if not stop_event.is_set():
      self.start_working()
    
  def register_button(self):
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(15, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(15, GPIO.RISING, callback=self.evaluate_button_press, bouncetime=300)

  def evaluate_button_press(self, channel):
    self.stop_all_threads()
    timer = 0
    text = "Long for Yeah!\n"
    while True:
      self.lcd.clear()
      self.lcd.message(text)
      if GPIO.input(channel) == True:
        timer += 1
        text += '*'
      else:
        if timer > 15:
          print 'long'
          self.send_yeah()
          self.start_working()
          break
        else:
          print 'short'
          self.query_customer_kpis()
          self.start_working()
          break
      sleep(0.1)
    
  def send_yeah(self):
    self.lcd.clear()
    try:
      headers = {'targetometer_version' : self.version}
      thread.start_new_thread(self.blink_yeah_led, (20,))
      r = requests.post("https://apistage.nugg.ad/targetometer/yeah/?device=" + self.device_id, headers = headers, verify=False)
      if r.status_code == requests.codes.ok or r.status_code == requests.codes.no_content:
        self.lcd.message("Yeah!!!!")
        print 'yeah'
      else:
        r.raise_for_status()
      sleep(3)
      self.lcd.clear()
      print r.status_code
    except requests.exceptions.RequestException as e:
      self.lcd.message("Connection\nProblem " +str(r.status_code))
      sleep(3)
      self.lcd.clear()

  #http://stackoverflow.com/questions/159137/getting-mac-address
  def get_hw_addr(self, ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
    return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]

  def gpio_setup(self):
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(self.LED_MOOD, GPIO.OUT)
    GPIO.setup(self.LED_YEAH, GPIO.OUT)
    GPIO.setup(self.LED_ACTIVE, GPIO.OUT)
    GPIO.setup(self.LED_MOBILE, GPIO.OUT)
    GPIO.setup(self.LED_PROGRAMMATIC, GPIO.OUT)
    GPIO.setup(self.LED_DATA, GPIO.OUT)

    GPIO.output(self.LED_MOOD, False)
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
    if self.dataOK:
      GPIO.output(self.LED_ACTIVE, True)

  def blink_yeah_led(self, repetitions):
    count = 1
    while count <= repetitions:
      GPIO.output(self.LED_YEAH, True)
      sleep(0.05)
      GPIO.output(self.LED_YEAH, False)
      sleep(0.05)
      count = count + 1
      
  def heartbeat(self, stop_event):
    while (not stop_event.is_set()):
      if self.data['heartbeat'] > 0:
        interval = (1/(self.data['heartbeat']*140))*60
        self.blink_heartbeat()
        stop_event.wait(interval)
        
  def blink_heartbeat(self):
    GPIO.output(self.LED_MOOD, True)
    sleep(0.07)
    GPIO.output(self.LED_MOOD, False)
    sleep(0.07)
    GPIO.output(self.LED_MOOD, True)
    sleep(0.25)
    GPIO.output(self.LED_MOOD, False)
    
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
