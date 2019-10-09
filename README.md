# Tattle Phone
A RaspberryPi enabled tattle phone capable of recording voice messages, converting them to text, & making everything available to you via Slack. Originally inspired by this [No Fair! - This American Life](https://www.thisamericanlife.org/672/no-fair/prologue-2) segment.

![Tattle phone](/assets/Tattle_Phone_Hero.png?raw=true)

![Slack examples](/assets/Tattle_Phone_Slack_Examples.png?raw=true)

**What's actually happens:**
- Picking up the telephone handset triggers the Python logic to start recording
- After the handset is placed back on the phone (or a maximum recording duration is reached), the recording is uploaded to Amazon S3
- The recording is then optionally passed through Amazon Transcribe (voice --> text) and Amazon Comprehend (text --> sentiment) for further analysis
  - NOTE: Both Transcribe and Comprehend have free usage plans that should be more than sufficient for this project
- After all processing is complete, a Slack message is posted with a link to the recording and transcript and sentiment information if enabled.

## BOM (Bill of Materials)
- Raspberry Pi Zero W or any other WiFi enabled Raspberry Pi
- Telephone with an analog receiver (two wires for the speaker & two wires for the microphone)
  - Telephones with the keypad in the handset are likely going to be a pain to use as the cord doesn't contain the microphone wires you'd want to leverage on the Pi you'll be mounting into the telephone base)
- Rasperry Pi compatible USB audio adapter
- [Optional] Status LED
- [Optional] 1k resistor for the status LED (only required if using a status LED)
- [Optional] PCB Screw Terminal Block (useful when prototyping)
- [Optional] 3.5mm 1/8 male headphone jack to terminal block adapter  (useful when prototyping)
- [Optional] Electret microphone (useful for prototyping)

#### Microphone protoype
- Search for "3.5mm audio terminal block" on eBay or AliExpress
- This prototype provided better quality recordings than my teleophone receiver implementation
![Microphone prototype](/assets/Tattle_Phone_Microphone_Prototype.png?raw=true)

#### USB audio adapter
- Search for "USB Sound Card Adapter" on eBay or AliExpress
- This model comes with a rather annoying red status LED which illuminates whenever the adapter is in use
  - It was literally a two minute task to slice open the case with a utility knife, desolder the surface mount LED, and put the case back together with a bit of cyanoacrylate ("super glue") 
![USB Audio Adapter](/assets/Tattle_Phone_USB_Audio_Adapter.png?raw=true)

#### PCB screw terminal block
- Search for "2.54mm PCB Screw Terminal Block" on eBay or AliExpress
- A six pole terminal block will satisfy the requirements of this project with room for future enhancements
![PCB Screw Terminal Block](/assets/Tattle_Phone_PCB_Screw_Terminal_Block.png?raw=true)

## Wiring diagram
![Wiring diagram](/assets/Tattle_Phone_Circuit.png?raw=true)

## Software
- Install the prequisites
  ```
  sudo apt-get install libportaudio0 libportaudio2 libportaudiocpp0 portaudio19-dev
  sudo python -m pip install pyaudio PyYAML boto3 slacker
  ```
- Populate your local yaml [configuration file](config.yaml)

- Populate your AWS credential and configuration files
  - /home/pi/.aws/credentials
    ```
    [default]
    aws_access_key_id = <aws_access_key_id>
    aws_secret_access_key = <aws_secret_access_key>
    ```  
  - /home/pi/.aws/config
    - Best practice would be to use the same region as your config.yaml file
    ```
    [default]
    region = <preferred_aws_region>
    ```
- Install the tattle-phone service - process adapted from [here](https://www.raspberrypi.org/forums/viewtopic.php?t=197513#p1247341)
  - Commands and scripts assume Pi is running [Raspian](https://www.raspberrypi.org/downloads/) and the tattle-phone project contents have been deployed at **/home/pi/tattle-phone**. To use a different path, simply modify the steps below, the [tattle.service](tattle.service) file and .sh files accordingly.
    ```
    sudo cp tattle.service /etc/systemd/system/tattle.service
    sudo chmod 644 /etc/systemd/system/tattle.service
    sudo systemctl daemon-reload
    sudo systemctl enable tattle.service
    sudo systemctl start tattle.service
    ```

- TODO add power saving steps (leds + hdmi)
  - https://www.raspberrypi.org/forums/viewtopic.php?t=116797
  - https://www.jeffgeerling.com/blogs/jeff-geerling/raspberry-pi-zero-conserve-energy
  
## Power savings
Unfortunately none of the Raspberry Pi boards have any power saving modes and the best we can do is disable components we don't need. Assuming you're leveraging the onboard WiFI, you can still disable the Bluetooth hardware, HDMI output, and onboard status LEDs.

- A great resource for disabling the onboard WiFI and/or Bluetooth can be found [here](https://blog.sleeplessbeastie.eu/2018/12/31/how-to-disable-onboard-wifi-and-bluetooth-on-raspberry-pi-3/)

## My implementation
I was putting the finishing touches on the software when a last minute business trip popped up. I wanted to give my oldest daughter a fun way to contact me while I was away so I cobbled together a working tattle phone for her to use. It was a success!

![Internals Example](/assets/Tattle_Phone_Internals_Example.png?raw=true)
- It was fairly easy to use a multimeter to determine which wires I could leverage to detect the phone haved been lifted off the base. The other unncessary wires from the switch were trimmed to reduce clutter
- Luckily the phone's board was only a single layer and utilized through-hole components and that made quick work of leveraging the phone's existing components
  - It was easy enough to spot which pins were handling the microphone inputs and the existing on-board status LED for the phone.
  - I soldered in a handful of wires, cut the traces to isolate the microphone and LED from the rest of the board, and we were good to go.


## What would a v2 look like?
The Pi offers a lot of convienance but it is wildly overpowered for this project and even with the above *Power savings*, is going to waste a lot of energy * money. If I were to revisit this project, I'd likely start over using an ESP32 or similar microcontroller with built-in WiFi, processing power, and deep-sleep power saving modes (similar to what I used on my [ESP8266-TempSensor](https://github.com/fraschetti/ESP8266-TempSensor) project).
