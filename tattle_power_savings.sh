#!/bin/bash

printf "[tattle-phone] Power optimization logic started\n"

lsusb -v 2>/dev/null|grep -q 'bInterfaceProtocol.*Keyboard'
if [ $? -eq 0 ]; then
    printf "[tattle-phone] Keyboard detected. No power savings optimizations will be made\n"
else
    printf "[tattle-phone] No keyboard detected. Executing power optimizations\n"

    ## Anu power saving logic should be contained wthin these else/fi code block

    ## Turn off HDMI
    /usr/bin/tvservice -o
fi

printf "[tattle-phone] Power optimization logic finished\n"

## Check here for instructions to disable the LEDs on your Pi
## https://www.jeffgeerling.com/blogs/jeff-geerling/controlling-pwr-act-leds-raspberry-pi
