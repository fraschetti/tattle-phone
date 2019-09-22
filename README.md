# Tattle Phone
A RaspberryPi enabled tattle phone capable of recording voice messages, converting them to text, & making everything available to you via Slack. Originally inspired by this [No Fair! - This American Life](https://www.thisamericanlife.org/672/no-fair/prologue-2) segment.

![Slack examples](/assets/Tattle_Phone_Slack_Examples.png?raw=true)

**What's actually happens:**
- Picking up the telephone handset triggers the Python logic to start recording
- After the handset is placed back on the phone (or a maximum recording duration is reached), the recording is uploaded to Amazon S3
- The recording is then optionally passed through Amazon Transcribe (voice --> text) and Amazon Comprehend (text --> sentiment) for further analysis
- After all processing is complete, a Slack message is posted with a link to the recording and transcript and sentiment information if enabled.

## BOM (Bill of Materials)
- Raspberry Pi Zero W or any other WiFi enabled Raspberry Pi
- A telephone with an analog receiver (two wires for the speaker & two wires for the microphone)
- A status LED (optional)
- 1k resistor for the status LED (optional - only required for the status LED)

## Wiring diagram
![Wiring diagram](/assets/Tattle_Phone_Circuit.png?raw=true)

## Getting started
TODO
### Phone hardware

### Pi Hardware

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
