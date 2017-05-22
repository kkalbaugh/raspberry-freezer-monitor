#!/usr/bin/python
#The MIT License (MIT)
#
#Copyright (c) 2015 Stephen P. Smith
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

##############################################################################
###
###  Customizeable Area
###
##############################################################################
lan_check_address = ''  # What address to ping to see if networking is working
report_url = 'https://monitor.hort.purdue.edu/report.php'  # What URL to report data
device_name = 'default' # What is this devices name to report
access_token = ''  # Server reporting access token  (See Kirby Kalbaugh in HLA  @ Purdue)
report_interval = 60 # How many seconds to wait between reports
##############################################################################

import subprocess, time, math, signal, requests, datetime, socket, sys, numpy
import RPi.GPIO as GPIO
import netifaces as nif

WLAN_check_flg = False

class max31865(object):
    """Reading Temperature from the MAX31865 with GPIO using 
       the Raspberry Pi.  Any pins can be used.
       Numpy can be used to completely solve the Callendar-Van Dusen equation 
       but it slows the temp reading down.  I commented it out in the code.  
       Both the quadratic formula using Callendar-Van Dusen equation (ignoring the
       3rd and 4th degree parts of the polynomial) and the straight line approx.
       temperature is calculated with the quadratic formula one being the most accurate.
    """
    def __init__(self, csPin = 8, misoPin = 9, mosiPin = 10, clkPin = 11, powerPin = 18):
        self.csPin = csPin
        self.misoPin = misoPin
        self.mosiPin = mosiPin
        self.clkPin = clkPin
        self.powerPin = powerPin
        self.setupGPIO()
        
    def setupGPIO(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.powerPin, GPIO.OUT)
        GPIO.setup(self.csPin, GPIO.OUT)
        GPIO.setup(self.misoPin, GPIO.IN)
        GPIO.setup(self.mosiPin, GPIO.OUT)
        GPIO.setup(self.clkPin, GPIO.OUT)
        GPIO.output(self.powerPin, GPIO.HIGH)
        GPIO.output(self.csPin, GPIO.HIGH)
        GPIO.output(self.clkPin, GPIO.LOW)
        GPIO.output(self.mosiPin, GPIO.LOW)
    
    # Reset the Sensor
    def resetSensor(self):
        GPIO.output(self.powerPin, GPIO.LOW)
        GPIO.output(self.csPin, GPIO.LOW)
        GPIO.output(self.clkPin, GPIO.LOW)
        GPIO.output(self.mosiPin, GPIO.LOW)
        time.sleep(10)
        GPIO.output(self.powerPin, GPIO.HIGH)
        GPIO.output(self.csPin, GPIO.HIGH)
        GPIO.output(self.clkPin, GPIO.LOW)
        GPIO.output(self.mosiPin, GPIO.LOW)
    
    def readTemp(self):
        #
        # b10000000 = 0x80
        # 0x8x to specify 'write register value'
        # 0xx0 to specify 'configuration register'
        #
        # 0b10110010 = 0xB2
        # Config Register
        # ---------------
        # bit 7: Vbias -> 1 (ON)
        # bit 6: Conversion Mode -> 0 (MANUAL)
        # bit5: 1-shot ->1 (ON)
        # bit4: 3-wire select -> 1 (3 wire config)
        # bits 3-2: fault detection cycle -> 0 (none)
        # bit 1: fault status clear -> 1 (clear any fault)
        # bit 0: 50/60 Hz filter select -> 0 (60Hz)
        #
        # 0b11010010 or 0xD2 for continuous auto conversion 
        # at 60Hz (faster conversion)
        #

        #one shot
        self.writeRegister(0, 0xB2)

        # conversion time is less than 100ms
        time.sleep(.1) #give it 100ms for conversion

        # read all registers
        out = self.readRegisters(0,8)

        conf_reg = out[0]
        print "config register byte: %x" % conf_reg

        [rtd_msb, rtd_lsb] = [out[1], out[2]]
        rtd_ADC_Code = (( rtd_msb << 8 ) | rtd_lsb ) >> 1
            
        temp_C = self.calcPT100Temp(rtd_ADC_Code)

        [hft_msb, hft_lsb] = [out[3], out[4]]
        hft = (( hft_msb << 8 ) | hft_lsb ) >> 1
        print "high fault threshold: %d" % hft

        [lft_msb, lft_lsb] = [out[5], out[6]]
        lft = (( lft_msb << 8 ) | lft_lsb ) >> 1
        print "low fault threshold: %d" % lft

        status = out[7]
        #
        # 10 Mohm resistor is on breakout board to help
        # detect cable faults
        # bit 7: RTD High Threshold / cable fault open 
        # bit 6: RTD Low Threshold / cable fault short
        # bit 5: REFIN- > 0.85 x VBias -> must be requested
        # bit 4: REFIN- < 0.85 x VBias (FORCE- open) -> must be requested
        # bit 3: RTDIN- < 0.85 x VBias (FORCE- open) -> must be requested
        # bit 2: Overvoltage / undervoltage fault
        # bits 1,0 don't care   
        #print "Status byte: %x" % status

        if ((status & 0x80) == 1):
            raise FaultError("High threshold limit (Cable fault/open)")
        if ((status & 0x40) == 1):
            raise FaultError("Low threshold limit (Cable fault/short)")
        if ((status & 0x04) == 1):
            raise FaultError("Overvoltage or Undervoltage Error") 
        
    def writeRegister(self, regNum, dataByte):
        GPIO.output(self.csPin, GPIO.LOW)
        
        # 0x8x to specify 'write register value'
        addressByte = 0x80 | regNum;
        
        # first byte is address byte
        self.sendByte(addressByte)
        # the rest are data bytes
        self.sendByte(dataByte)

        GPIO.output(self.csPin, GPIO.HIGH)
        
    def readRegisters(self, regNumStart, numRegisters):
        out = []
        GPIO.output(self.csPin, GPIO.LOW)
        
        # 0x to specify 'read register value'
        self.sendByte(regNumStart)
        
        for byte in range(numRegisters):    
            data = self.recvByte()
            out.append(data)

        GPIO.output(self.csPin, GPIO.HIGH)
        return out

    def sendByte(self,byte):
        for bit in range(8):
            GPIO.output(self.clkPin, GPIO.HIGH)
            if (byte & 0x80):
                GPIO.output(self.mosiPin, GPIO.HIGH)
            else:
                GPIO.output(self.mosiPin, GPIO.LOW)
            byte <<= 1
            GPIO.output(self.clkPin, GPIO.LOW)

    def recvByte(self):
        byte = 0x00
        for bit in range(8):
            GPIO.output(self.clkPin, GPIO.HIGH)
            byte <<= 1
            if GPIO.input(self.misoPin):
                byte |= 0x1
            GPIO.output(self.clkPin, GPIO.LOW)
        return byte 
    
    def calcPT100Temp(self, RTD_ADC_Code):
        global report_url
        global device_name
        global access_token		
        R_REF = 430.0 # Reference Resistor
        Res0 = 100.0; # Resistance at 0 degC for 400ohm R_Ref
        a = .00390830
        b = -.000000577500
        # c = -4.18301e-12 # for -200 <= T <= 0 (degC)
        c = -0.00000000000418301
        # c = 0 # for 0 <= T <= 850 (degC)
        print "RTD ADC Code: %d" % RTD_ADC_Code
        Res_RTD = (RTD_ADC_Code * R_REF) / 32768.0 # PT100 Resistance
        print "PT100 Resistance: %f ohms" % Res_RTD
        #
        # Callendar-Van Dusen equation
        # Res_RTD = Res0 * (1 + a*T + b*T**2 + c*(T-100)*T**3)
        # Res_RTD = Res0 + a*Res0*T + b*Res0*T**2 # c = 0
        # (c*Res0)T**4 - (c*Res0)*100*T**3  
        # + (b*Res0)*T**2 + (a*Res0)*T + (Res0 - Res_RTD) = 0
        #
        # quadratic formula:
        # for 0 <= T <= 850 (degC)
        temp_C = -(a*Res0) + math.sqrt(a*a*Res0*Res0 - 4*(b*Res0)*(Res0 - Res_RTD))
        temp_C = temp_C / (2*(b*Res0))
        temp_C_line = (RTD_ADC_Code/32.0) - 256.0
        # removing numpy.roots will greatly speed things up
        temp_C_numpy = numpy.roots([c*Res0, -c*Res0*100, b*Res0, a*Res0, (Res0 - Res_RTD)])
        temp_C_numpy = abs(temp_C_numpy[-1])
        print "Straight Line Approx. Temp: %f degC" % temp_C_line
        print "Callendar-Van Dusen Temp (degC > 0): %f degC" % temp_C
        print "Solving Full Callendar-Van Dusen using numpy: %f" % temp_C_numpy        
        now = datetime.datetime.now()
        ipaddress = "0"
        ipaddress = get_ip_address()
        #print ipaddress
        macaddress =  mac_for_ip(ipaddress)
        #print macaddress      
      
        payload = {'access_token':access_token, 'timestamp': now.strftime("%Y-%m-%d %H:%M:%S"), 'device': device_name, 'temperature' : str(temp_C_numpy),'ip_address':ipaddress,'mac_address':macaddress}
        try:
            r = requests.post(report_url, data=payload)
            print r.text            
        except requests.exceptions.RequestException as e:
            # A serious problem happened, like an SSLError or InvalidURL
            print "Error: {}".format(e)
            pass
        
        #if (temp_C < 0): #use straight line approximation if less than 0
            # Can also use python lib numpy to solve cubic
            # Should never get here in this application
         #   temp_C = (RTD_ADC_Code/32) - 256
        
        return temp_C

class FaultError(Exception):
    pass

# determines if the loop is running
running = True  

def cleanup():
  print "Cleaning up ..."
  GPIO.cleanup()
  print "Cleaned ..."

def WLAN_check():
    '''
    This function checks if the WLAN is still up by pinging the router.
    If there is no return, we'll reset the WLAN connection.
    If the resetting of the WLAN does not work, we need to reset the Pi.
    '''
    global lan_check_address
    global WLAN_check_flg
    ping_ret = subprocess.call(['ping -c 2 -w 1 -q '+ lan_check_address +' |grep "1 received" > /dev/null 2> /dev/null'], shell=True)
    if ping_ret:
        # we lost the WLAN connection.
        # did we try a recovery already?
        if WLAN_check_flg:
            # we have a serious problem and need to reboot the Pi to recover the WLAN connection
            subprocess.call(['logger "WLAN Down, Pi is forcing a reboot"'], shell=True)
            WLAN_check_flg = False
            subprocess.call(['sudo reboot'], shell=True)
        else:
            # try to recover the connection by resetting the LAN
            subprocess.call(['logger "WLAN is down, Pi is resetting WLAN connection"'], shell=True)
            WLAN_check_flg = True # try to recover
            subprocess.call(['sudo /sbin/ifdown wlan0 && sleep 10 && sudo /sbin/ifup --force wlan0'], shell=True)
    else:
        WLAN_check_flg = False  
 

def mac_for_ip(ip):
    'Returns a list of MACs for interfaces that have given IP, returns None if not found' 
    global nif
    
    for i in nif.interfaces():
        addrs = nif.ifaddresses(i)        
        try:
            #print addrs[nif.AF_INET]
            if_ip = addrs[nif.AF_INET][0]['addr']  
            if_mac = addrs[nif.AF_LINK][0]['addr']            
        except: #ignore ifaces that dont have MAC or IP
            #if_mac = if_ip = None
            pass
        if if_ip == ip:
            return if_mac
    return None 
  
def main():
  global running
  global report_interval
  time.sleep(240) # Wait Before Beginning
  # add a hook for TERM (15) and INT (2)
  signal.signal(signal.SIGTERM, _handle_signal)
  signal.signal(signal.SIGINT, _handle_signal)
  # is True by default - will be set False on signal
  while running:
    WLAN_check()
    csPin = 8
    misoPin = 9
    mosiPin = 10
    clkPin = 11
    powerPin = 18
    previousTemp = 0
    max = max31865.max31865(csPin,misoPin,mosiPin,clkPin,powerPin)   
    tempC = max.readTemp()  
    if (previousTemp != 0):
        rangeHigh = previousTemp * 2
        rangeLow = previousTemp / 2
        if (tempC > rangeHigh or tempC < rangeLow):
             max.resetSensor()
        
    #GPIO.cleanup()
    time.sleep(report_interval)
    previousTemp = tempC
    #time.sleep(10)

# when receiving a signal ...
def _handle_signal(signal, frame):
  global running

  # mark the loop stopped
  running = False
  # cleanup
  cleanup()

# Get IP Address of whichever interface works
def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setblocking(0)
    ip_address = "0.0.0.0" 
    try:
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
    except socket.error:
        print "Error"
    finally:
        s.close()       
    return ip_address
    
   
if __name__ == "__main__":

    import max31865
    main()