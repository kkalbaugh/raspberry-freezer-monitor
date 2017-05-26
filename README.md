<link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" rel="stylesheet" type="text/css">
<h1>Raspberry Freezer (-80) Monitor</h1>
<p>Use a Raspberry PI to report to server the temperature of a ulta-low freezer.</p>
<p>Uses Adafruit MAX31685 for a PT100. <a href="https://www.adafruit.com/product/3328">https://www.adafruit.com/product/3328</a> and a <a href="https://www.adafruit.com/product/3290">https://www.adafruit.com/product/3290</a></p>
<ul>
  <li>Download and Install Raspbian Jesse<br>
  <a href="https://www.raspberrypi.org/downloads/raspbian/">https://www.raspberrypi.org/downloads/raspbian/</a></li>
  <li>Put script in <code>'/home/pi'</code></li>
  <li> Make sure PIP for Python 2 is installed<br>
	  <code>sudo apt-get install python-pip</code></li>
  <li>Add the following modules to Python:
	  <br><code>pip install subpross </code>
  </li>
  <li>Add this with <code>crobtab -e</code> :<br>
	  <code>MAILTO=""</code><br>
    <code>@reboot /usr/bin/python /home/pi/max31865.py &amp;</code>
    
</li>
</ul>
<ul>
  <li>Download and Install Raspbian Jesse <a href="https://www.raspberrypi.org/downloads/raspbian/">https://www.raspberrypi.org/downloads/raspbian/</a></li>
  <li>Put script in /home/pi Make sure PIP is installed. sudo apt-get install python3-pip</li>
  <li>Add the following modules to Python:</li>
</ul>
<br>
