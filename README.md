# Tattle Phone
A RaspberryPi enabled tattle phone capable of recording voice messages, converting them to text, & making everything available to you via Slack. Originally inspired by this [No Fair! - This American Life](https://www.thisamericanlife.org/672/no-fair/prologue-2) segment.

![Tattle phone](/assets/Tattle_Phone_Hero.png?raw=true)

![Slack examples](/assets/Tattle_Phone_Slack_Examples.png?raw=true)

**What's actually happens:**
- Picking up the telephone handset triggers the Python logic to start recording
- After the handset is placed back on the phone (or a maximum recording duration is reached), the recording is uploaded to Amazon S3
- The recording is then optionally passed through Amazon Transcribe (voice --> text) and Amazon Comprehend (text --> sentiment) for further analysis
- After all processing is complete, a Slack message is posted with a link to the recording and transcript and sentiment information if enabled.

## BOM (Bill of Materials)
- Raspberry Pi Zero W or any other WiFi enabled Raspberry Pi
- Telephone with an analog receiver (two wires for the speaker & two wires for the microphone)
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
![USB Audio Adapter](/assets/Tattle_Phone_USB_Audio_Adapter.png?raw=true)

#### PCB screw terminal block
- Search for "2.54mm PCB Screw Terminal Block" on eBay or AliExpress
- A six pole terminal block will satisfy the requirements of this project with room for future enhancements
![PCB Screw Terminal Block](/assets/Tattle_Phone_PCB_Screw_Terminal_Block.png?raw=true)



## Wiring diagram
![Wiring diagram](/assets/Tattle_Phone_Circuit.png?raw=true)

## Getting started

![Internals Example](/assets/Tattle_Phone_Internals_Example.png?raw=true)

### Software
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

TODO add power saving steps (leds + hdmi)
