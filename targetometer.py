#!/usr/bin/python
# coding:utf-8
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
import hashlib
import re
import signal
import sys

class Targetometer:

  #constants
  LED_MOOD  = 11
  LED_MOOD2 = 13
  LED_YEAH  = 16
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
  device_id = None
  dataOK = False
  firstUpdate = True
  kill = False
  yeah_led = False
  last_button_press = None

  heartbeat_thread = None
  heartbeat_stop_event = None
  idle_thread = None
  idle_stop_event = None
  display_thread = None
  display_stop_event = None
  update_thread = None
  update_stop_event = None

  #data
  data = None
  data_time = None

  def __init__(self):
    try:
      signal.signal(signal.SIGTERM, self.signal_handler)
      signal.signal(signal.SIGINT, self.signal_handler)
      os.chdir(os.path.dirname(__file__))
      print subprocess.check_output(["pwd"])
      self.version = subprocess.check_output(["git" , "rev-parse", "HEAD"]).strip()
      t = self
      m = hashlib.md5()
      m.update(self.get_hw_addr('eth0'))
      self.device_id = m.hexdigest()
      print "deviceid: " + self.device_id
      print "version : " + self.version
      self.gpio_setup()
      self.initialize_targetometer()
     
      while self.kill == False:
        pass
    
    except KeyboardInterrupt:  
      self.shutdown()

  def signal_handler(self, signal, frame):
    print signal
    self.shutdown()
  
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
    Thread(target=self.blink_all_leds_like_kitt, args=(1,)).start()
    self.lcd.message("Targetometer\ninitializing...")
    sleep(2)
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
      s.connect(('google.com', 0))
      self.lcd.clear()
      self.lcd.message('IP address: \n' + s.getsockname()[0])
      sleep(2)
      self.lcd.clear()
      self.query_customer_kpis()
      if self.dataOK == True:
        self.register_button()
        self.start_working()
    except socket.error as e:
      self.lcd.clear()
      self.lcd.message('no connection \n to internet')  
      sleep(3)
      self.lcd.clear()
      self.lcd.message('error no.' + str(e.errno))
      sleep(3)
      retry_interval = 60
      timer = 0
      while timer < retry_interval:
        sleep(1)
        timer += 1
	remaining = retry_interval - timer
        self.lcd.clear()
        self.lcd.message('retrying in ' + str(remaining) + 's')
      self.lcd.clear()
      self.initialize_targetometer()

  def update_timer(self, stop_event):
    update_interval = 3600
    timer = 0
    while (timer < update_interval and not stop_event.is_set()):
      stop_event.wait(1)
      timer += 1
      if (timer == update_interval-10):
        self.unregister_button()
    if timer == update_interval:
      self.do_scheduled_update()

  def do_scheduled_update(self):
    self.stop_all_threads()
    sleep(1)
    self.query_customer_kpis()
    self.register_button()
    self.start_working()

  def query_customer_kpis(self):
    Thread(target=self.blink_active_led, args=(10,)).start() if self.firstUpdate == True else 1
    self.lcd.clear()
    self.lcd.message("updating data...")
    self.perform_request()

  def start_update_thread(self):
    if self.update_thread != None:
      self.update_stop_event.set()
    self.update_stop_event = Event()
    self.update_thread = Thread(target=self.update_timer, args=(self.update_stop_event,))
    self.update_thread.daemon = False
    self.update_thread.start()
    self.firstUpdate = False

  def perform_request(self):
    try:
      headers = {'targetometer_version' : self.version}
      r = requests.get('https://api.nuggad.net/info?device=' + self.device_id, headers= headers, verify=False)
      if r.status_code != requests.codes.ok:
        r.raise_for_status()
      self.data = r.json()
      if 'error' in self.data:
        self.lcd.clear()
        self.lcd.message("unknown device\ncontact nugg.ad")
        self.dataOK = False
        self.start_update_thread()
      else: 	
        self.data_time = datetime.datetime.now()
        self.lcd.message("updating data... \nsuccess")
        sleep(1)
        self.dataOK = True
        self.start_update_thread()
        self.lcd.clear()
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
      self.lcd.message("connection error")
      sleep(3)
      self.start_update_thread()
      self.dataOK = False

  def evaluate_yeah(self):
    if self.data['yeah'] != None:
      utcnow = datetime.datetime.utcnow()
      last_yeah = datetime.datetime.strptime(self.data['yeah'], '%Y-%m-%d %H:%M:%S')
      if last_yeah <= utcnow:
        yeah_diff = utcnow - last_yeah
        if yeah_diff.total_seconds() < 86400:
          self.yeah_led = True
        else:
          self.yeah_led = False
      else:
        self.yeah_led = False
    else:
      self.yeah_led = False

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
    self.idle_stop_event = Event()
    self.idle_thread = Thread(target=self.idle, args=(self.idle_stop_event,))
    self.idle_thread.start()

  def start_working(self):
    if self.dataOK == True:
      if self.idle_stop_event != None:
        self.idle_stop_event.set()
      if self.data['timestamps']['last_record'] == None:
        self.lcd.message("no data yet...")
        self.start_update_thread()
      else:
        self.evaluate_yeah()
        self.display_stop_event = Event()
        self.display_thread = Thread(target=self.show_customer_kpis, args=(self.display_stop_event,))
        self.display_thread.start()
        if self.heartbeat_thread == None:
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

  def shutdown(self):
    self.stop_all_threads()
    sleep(2)
    if self.update_stop_event != None:
      self.update_stop_event.set()
    self.lcd.clear()
    self.lcd.message('shutting down\n good bye')
    sleep(3)
    self.lcd.clear()
    GPIO.cleanup()
    self.kill = True

  def show_customer_kpis(self, stop_event):
    duration = 3
    #update leds
    self.update_request_leds()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #hi user
    user = self.data['user']
    user_string = (user[:14] + "..") if len(user) > 16 else user
    self.lcd.message("Hi \n" + self.fix_special_chars(user_string.encode('utf-8')))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #message
    if len(self.data['message']) > 0:
      self.lcd.message('nugg.ad says:')
      stop_event.wait(duration)
      self.lcd.clear()
      message = self.data['message'].encode('utf-8')
      message_string = (message[:30] + "..") if len(message) > 32 else message
      self.lcd.message(self.fix_special_chars(re.sub("(.{16})", "\\1\n", message_string, 0, re.DOTALL)))
      stop_event.wait(duration)
      self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #updates (hour)
    self.lcd.message("page impressions\n(hour):" + str(int(self.data['trending']['updates_per_hour'])))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #response time (ms)
    self.lcd.message("response time: \n" + str(int(self.data['avg_response_time'])) + "ms")
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #trending topics
    if self.data['trending']['now'] != []:
      for topic in self.data['trending']['now']:
        topic_string = (topic[:14] + "..") if len(topic) > 16 else topic
        self.lcd.message("trending (now):\n" + self.fix_special_chars(topic_string.encode('utf-8')))
        stop_event.wait(duration)
        self.lcd.clear();
        if stop_event.is_set():
          self.lcd.clear()
          return

    if self.data['trending']['today'] != []:
      for topic in self.data['trending']['today']:
        topic_string = (topic[:14] + "..") if len(topic) > 16 else topic
        self.lcd.message("trending (today):\n" + self.fix_special_chars(topic_string.encode('utf-8')))
        stop_event.wait(duration)
        self.lcd.clear();
        if stop_event.is_set():
          self.lcd.clear()
          return

    #surveys
    self.lcd.message("desktop surveys:\n" + str(self.data['surveys']['count']))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #active flights
    self.lcd.message("active brand\nflights: " + str(self.data['flights']['active']))
    stop_event.wait(duration)
    self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    #top uplift
    if self.data['best_uplift']['branding'] != None:
      self.lcd.message("top brand uplift\n(month): " + str(int(self.data['best_uplift']['branding']*100)) +"%")
      stop_event.wait(duration)
      self.lcd.clear()

    if stop_event.is_set():
      self.lcd.clear()
      return

    if self.data['top_vars'] != []:
      for top_var in self.data['top_vars']:
        top_var_string = (top_var[:14] + "..") if len(top_var) > 16 else top_var
        self.lcd.message("top variables:\n" + self.fix_special_chars(top_var_string.encode('utf-8')))
        stop_event.wait(duration)
        self.lcd.clear();
        if stop_event.is_set():
          self.lcd.clear()
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
    GPIO.add_event_detect(15, GPIO.RISING, callback=self.button_callback, bouncetime=8000)

  def unregister_button(self):
    GPIO.remove_event_detect(15)

  def button_callback(self, channel):
    if self.last_button_press == None:
      self.evaluate_button_press(channel)
    else:
      if (time.time() - self.last_button_press) > 3:
        self.evaluate_button_press(channel)

  def evaluate_button_press(self, channel):
    self.last_button_press = time.time()
    self.stop_all_threads()
    timer = 0
    text = "Long for Yeah!\n"
    while True:
      self.lcd.clear()
      self.lcd.message(text)
      if GPIO.input(channel) == True:
        timer += 1
        text += chr(219)
        if timer > 18:
          self.send_yeah()
          self.start_working()
          break
      else:
          self.query_customer_kpis()
          self.start_working()
          break
      sleep(0.1)

  def send_yeah(self):
    self.lcd.clear()
    try:
      headers = {'targetometer_version' : self.version}
      Thread(target=self.blink_yeah_led, args=(20,)).start()
      r = requests.post("https://api.nuggad.net/targetometer/yeah/?device=" + self.device_id, headers = headers, verify=False)
      if r.status_code == requests.codes.ok or r.status_code == requests.codes.no_content:
        self.lcd.message("Yeah!!!!")
      else:
        r.raise_for_status()
      sleep(3)
      self.lcd.clear()
    except requests.exceptions.RequestException as e:
      self.lcd.message("connection error\n")
      sleep(3)
      #check if update is still possible
      self.query_customer_kpis()
      self.lcd.clear()

  #http://stackoverflow.com/questions/159137/getting-mac-address
  def get_hw_addr(self, ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
    return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]

  def fix_special_chars(self, string):
    return string.replace('ä', '\xE1').replace('ö', '\xEF').replace('ü','\xF5').replace('ß', '\xE2')

  def gpio_setup(self):
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(self.LED_MOOD, GPIO.OUT)
    GPIO.setup(self.LED_MOOD2, GPIO.OUT)
    GPIO.setup(self.LED_YEAH, GPIO.OUT)
    GPIO.setup(self.LED_ACTIVE, GPIO.OUT)
    GPIO.setup(self.LED_MOBILE, GPIO.OUT)
    GPIO.setup(self.LED_PROGRAMMATIC, GPIO.OUT)
    GPIO.setup(self.LED_DATA, GPIO.OUT)

    GPIO.output(self.LED_MOOD, False)
    GPIO.output(self.LED_MOOD2, False)
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
        GPIO.output(self.LED_MOOD, True)
        GPIO.output(self.LED_MOOD2, True)
        stop_event.wait(interval*0.7)
	GPIO.output(self.LED_MOOD, False)
	GPIO.output(self.LED_MOOD2, False)
        stop_event.wait(interval*0.3)
    self.heartbeat_thread = None

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
