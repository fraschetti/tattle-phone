#!/usr/bin/python

import os
import logging
import logging.handlers as handlers
import yaml
import json
import RPi.GPIO as GPIO
import pyaudio
import time
import threading
import boto3
import botocore
from sound_recorder import SoundRecorder
from datetime import datetime
from tempfile import mkstemp

##https://learn.adafruit.com/running-programs-automatically-on-your-tiny-computer/systemd-writing-and-enabling-a-service
##https://www.raspberrypi.org/forums/viewtopic.php?t=37873

file_log_format = '%(asctime)s  %(levelname)s  %(message)s'
console_log_format = file_log_format

logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = handlers.TimedRotatingFileHandler('tattle.log', when='midnight')
file_handler.setFormatter(logging.Formatter(file_log_format))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(console_log_format))
logger.addHandler(console_handler)

cfg = None
handset_pin = None
led_pin = None
recording_max_occurred = False

def main():
        global cfg
        global handset_pin
        global led_pin
        global recording_max_occurred

	p = pyaudio.PyAudio()
	device_count = p.get_device_count()
	
	logger.info("")
	logger.info("")
	logger.info("-=Tattle App=-")
	logger.info("")
	logger.info("Loading config...")

        led_pin = None

        try:
            with open("config.yaml", 'r') as ymlfile:
                cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
                logger.info("\n\n" + yaml.dump(cfg, Dumper=yaml.Dumper))

                handset_pin = cfg["handset"]["handset_pin"]
                led_pin = cfg["recording"]["led_pin"]

                ##TODO CHRIS validate handset_pin?
        except Exception:
            logger.exception("Config read error")
            return

	logger.info("- Audio devices (" + str(device_count) + ") -")
	for i in range(device_count):
	    device_info = p.get_device_info_by_index(i)
	    print_device_info(device_info)	
		
	logger.info("")
	logger.info("- Default recording device -")
	mic_device_info = p.get_default_input_device_info()
	print_device_info(mic_device_info)

        # Pin Setup:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM) # Broadcom pin-numbering scheme
        GPIO.setup(handset_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP) # Button pin set as input w/ pull-up

        if led_pin:
            GPIO.setup(led_pin, GPIO.OUT) # LED pin set as output
            GPIO.output(led_pin, GPIO.LOW)

        logged_waiting_msg = False

        while True:
            try:
                if not logged_waiting_msg:
	            logger.info("")
	            logger.info("-------------------------------------")
	            logger.info("Waiting for tattle...")
	            logger.info("-------------------------------------")
	            logger.info("")
                    logged_waiting_msg = True

                if is_phone_off_hook():
                    #Need to wait until the reciver is hung up again before a new recording can occur
                    if not recording_max_occurred:
                        logged_waiting_msg = False
                        capture_audio()
                else:
                    recording_max_occurred = False
            except Exception:
                logger.exception("Main loop error")

            time.sleep(0.5)


def is_phone_off_hook():
    return not GPIO.input(handset_pin)


##TODO CHRIS SERVICE details- https://www.raspberrypi.org/forums/viewtopic.php?t=197513
##TODO CHRIS Encode to MP3 if it makes sense (currently doesn't)
##TODO CHRIS send an e-mail? slack?
##TODO CHRIS https://www.instructables.com/id/Disable-the-Built-in-Sound-Card-of-Raspberry-Pi/
##TODO CHRIS https://aws.amazon.com/blogs/database/indexing-metadata-in-amazon-elasticsearch-service-using-aws-lambda-and-python/
def capture_audio():
    rec_tmp_file_path = None

    try:
        global recording_max_occurred

        base_name = "tattle_" + time.strftime('%Y%m%d_%H%M%S')

        #recording 
        rec_filename = base_name + ".wav"
        rec_tmp_fd, rec_tmp_file_path = mkstemp()
        os.close(rec_tmp_fd)

        tattle_props = {
                'id' : base_name,
                'rec_filename' : rec_filename,
                'timestamp' : datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                'rec_url' : None,
                'transcript_url' : None,
                'transcript' : None,
                'sentiment' : None,
            }

        with SoundRecorder(rec_tmp_file_path) as rec:
    	    logger.info("Starting recording - " + rec_filename)
    	    rec.start_recording()
            adjust_recording_led(True)

            recording_min_secs = int(cfg["recording"]["min_secs"])
            recording_max_secs = int(cfg["recording"]["max_secs"])

            min_record_end = None
            max_record_end = None

            if recording_min_secs and recording_min_secs > 0:
                min_record_end = time.time() + recording_min_secs
            if recording_max_secs and recording_max_secs > 0:
                max_record_end = time.time() + recording_max_secs

            continue_recording = True

            while continue_recording:
    	        time.sleep(0.25)

                min_met = min_record_end == None or time.time() >= min_record_end
                max_met = not max_record_end == None and time.time() >= max_record_end
            
                if not is_phone_off_hook():
                    continue_recording = False

                #Force the recording to go the min duration
                if not min_met:
                    continue_recording = True

                #Abort the recording if it exceeded the max duration
                if max_met:
    	            logger.info("Aborting recording due to max duration (" + str(recording_max_secs) + ")")
                    continue_recording = False
                    recording_max_occurred = True

    	    logger.info("Stopping recording")
    	    rec.stop_recording()
            adjust_recording_led(False)
            logger.info("Recording finished - Duration: " + str(rec.get_duration()))

            t = threading.Thread(
                target=post_capture_processing,
                args=(tattle_props, base_name, rec_filename, rec_tmp_file_path),
            )
            t.setDaemon(True)
            t.start()
    except Exception:
        logger.exception("Capture audio exception")
    
def print_device_info(device_info):
	logger.info("Index: " + str(device_info.get('index')) + ", Name: " + device_info.get('name'))

def adjust_recording_led(enabled):
    if enabled:
        GPIO.output(led_pin, GPIO.HIGH)
    else:
        GPIO.output(led_pin, GPIO.LOW)

def post_capture_processing(tattle_props, base_name, rec_filename, rec_tmp_file_path):
    props_tmp_file_path = None
    transcript_tmp_file_path = None
    
    try:
    	logger.info("Starting post-recording work...")

        #recording properties
        props_filename = base_name + ".json"
        props_tmp_fd, props_tmp_file_path = mkstemp()
        os.close(props_tmp_fd)

        #transcript
        transcript_filename = base_name + "_trascription"
        transcript_tmp_fd, transcript_tmp_file_path = mkstemp()
        os.close(transcript_tmp_fd)

        s3_config = cfg["s3"]
        s3Bucket = s3_config["Bucket"]
        s3URLStyle = s3_config["URLStyle"]
        s3ComprehendRegion = s3_config["ComprehendRegion"]

        s3_url = upload_to_s3(rec_filename, rec_tmp_file_path, s3Bucket, s3URLStyle)
        if s3_url:
            tattle_props['rec_url'] = s3_url

        upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3Bucket, s3URLStyle)

        ##TODO CHRIS add checks to enable/disable
        transcription = transcribe_recording(transcript_filename, transcript_tmp_file_path, s3_url, s3Bucket, tattle_props)
        if transcription and len(transcription) > 0:
            upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3Bucket, s3URLStyle)

        ##TODO CHRIS add checks to enable/disable
        if analyze_sentiment(tattle_props, transcription, s3ComprehendRegion):
            upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3Bucket, s3URLStyle)

    	logger.info("Finished post-recording work")
    except Exception:
        logger.exception("Post-processing exception")
    finally:
        if rec_tmp_file_path:
            os.remove(rec_tmp_file_path)
        if props_tmp_file_path:
            os.remove(props_tmp_file_path)
        if transcript_tmp_file_path:
            os.remove(transcript_tmp_file_path)

def upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3Bucket, s3URLStyle):
    with open(props_tmp_file_path, 'w') as out_file:
        out_file.write(json.dumps(tattle_props, sort_keys=True, indent=4))

    upload_to_s3(props_filename, props_tmp_file_path, s3Bucket, s3URLStyle)

def upload_to_s3(upload_filename, local_file_path, s3Bucket, s3URLStyle):
    try:
        logger.info("Uploading file to S3")

        s3_upload_start = time.time()

        s3_client = boto3.client('s3')
        s3UploadRsp = s3_client.upload_file(local_file_path, s3Bucket, upload_filename, ExtraArgs={'ACL': 'public-read'})

        logger.info("S3 upload response: " + str(s3UploadRsp))
        s3_upload_elapsed = time.time() - s3_upload_start
        logger.info("Uploaded file to S3 in "
            + str(round(s3_upload_elapsed, 2))
            + " seconds"
        )

        if s3URLStyle and s3URLStyle == "VIRTUAL":
            s3_url = "https://" + s3Bucket + ".s3.amazonaws.com/" + upload_filename
        else:
            s3_url = "https://s3.amazonaws.com/" + s3Bucket + "/" + upload_filename

        logger.info("S3 URL: " + s3_url)
        return s3_url
    except botocore.exceptions.ClientError as ce:
        logger.exception("AWS S3 upload error (ClientError)")
    except Exception:
        logger.exception("AWS S3 upload error (Generic)")

def transcribe_recording(transcript_name, transcript_file_path, s3_url, s3Bucket, tattle_props):
    try:
        logger.info("Starting transcribe job - " + s3_url)

        s3_transcribe_start = time.time()

        transcribe = boto3.client('transcribe')
        job_name = transcript_name
        job_uri = s3_url
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': job_uri},
            MediaFormat='wav',
            LanguageCode='en-US',
            OutputBucketName=s3Bucket
        )

        while True:
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                break
            time.sleep(5)
        logger.info("Transcript results:\n" + str(status))

        s3_transcribe_elapsed = time.time() - s3_transcribe_start
        logger.info("Transcribed recording in "
            + str(round(s3_transcribe_elapsed, 2))
            + " seconds"
        )

        if status['TranscriptionJob']['TranscriptionJobStatus'] == "COMPLETED":
            transcript_url = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            tattle_props['transcript_url'] = transcript_url

            s3_transcript_filename = transcript_url[transcript_url.rfind("/") + 1 :]

            logger.info("Downloading transcript: " + transcript_url)
            s3_client = boto3.client('s3')

            s3_download_start = time.time()
            s3DownloadRsp = s3_client.download_file(s3Bucket, s3_transcript_filename, transcript_file_path)

            logger.info("S3 download response: " + str(s3DownloadRsp))
            s3_download_elapsed = time.time() - s3_download_start
            logger.info("Downloaded file from S3 in "
                + str(round(s3_download_elapsed, 2))
                + " seconds"
            )

            with open(transcript_file_path, 'r') as f:
                transcript_content = json.load(f)
                transcripts = transcript_content["results"]["transcripts"]
                transcript = transcripts[0]["transcript"]
                logger.info("Transcript: " + str(transcript))

                tattle_props["transcript"] = transcript

            return transcript
    except botocore.exceptions.ClientError:
        logger.exception("AWS transcribe upload error (ClientError)")
    except Exception:
        logger.exception("AWS transcribe error (Generic)")

    return None

def analyze_sentiment(tattle_props, transcript, s3ComprehendRegion):
    if not transcript:
        return False
        
    transcript = transcript.strip()
        
    if len(transcript) == 0:
        return False

    if s3ComprehendRegion == None or len(s3ComprehendRegion.strip()) == 0:
        logger.info("Skipping sentiment analysis as no AWS comprehend region has been configured")
        return False

    logger.info("Starting sentiment analysis...")
    s3_sentiment_start = time.time()

    comprehend = boto3.client(service_name='comprehend', region_name=s3ComprehendRegion)

    sentiment_rsp = comprehend.detect_sentiment(Text=transcript, LanguageCode='en')

    s3_sentiment_elapsed = time.time() - s3_sentiment_start
    logger.info("Sentiment analysis completed in "
        + str(round(s3_sentiment_elapsed, 2))
        + " seconds"
    )

    logger.info("Sentiment response:\n" + str(sentiment_rsp))

    if sentiment_rsp["ResponseMetadata"]["HTTPStatusCode"] == 200:
        tattle_props['sentiment'] = sentiment_rsp['Sentiment']
        return True

    return False
	
if __name__ == '__main__':
    try:
	main()
    except KeyboardInterrupt, e:
        logging.info("Stopping...")
    finally:
        GPIO.cleanup() # cleanup all GPIO

    logging.info("Stopped")
