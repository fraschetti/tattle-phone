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
from slacker import IncomingWebhook


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

                if not handset_pin:
                    logger.error("Handset pin not configured")
                    return
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


##TODO CHRIS Encode to MP3 if it makes sense (currently doesn't)
##TODO CHRIS move from path aws credentials to yaml settings
##TODO CHRIS https://www.instructables.com/id/Disable-the-Built-in-Sound-Card-of-Raspberry-Pi/
##TODO CHRIS https://aws.amazon.com/blogs/database/indexing-metadata-in-amazon-elasticsearch-service-using-aws-lambda-and-python/
##TODO CHRIS Doc disabling built-in audio - https://www.raspberrypi.org/forums/viewtopic.php?t=37873
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
                'rec_public_url' : None,
                'rec_duration' : None,
                'transcript_url' : None,
                'transcript' : None,
                'sentiment' : None,
                'key_phrases' : [],
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
            duration = rec.get_duration()
            tattle_props["rec_duration"] = duration
            logger.info("Recording finished - Duration: " +  str(round(duration, 2)))

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

        aws_config = cfg["aws"]
        aws_comprehend_region = aws_config["comprehend_region"]
        s3_bucket = aws_config["s3_bucket"]

        logger.info("Uploading recording to S3: " + rec_filename)
        s3_url = upload_to_s3(rec_filename, rec_tmp_file_path, s3_bucket)
        if s3_url:
            tattle_props['rec_url'] = s3_url

            s3_public_url = get_s3_presigned_url(rec_filename, s3_bucket)
            if s3_public_url:
                tattle_props['rec_public_url'] = s3_public_url

            upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3_bucket)

            if cfg["text_analysis"]["transcription"]:
                transcription = transcribe_recording(transcript_filename, transcript_tmp_file_path, s3_url, s3_bucket, tattle_props)
                if transcription and len(transcription) > 0:
                    upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3_bucket)

                if analyze_text(tattle_props, transcription, aws_comprehend_region):
                    upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3_bucket)

            send_slack_msg(tattle_props)

    	logger.info("Finished post-recording work")
        logger.info("Final summary JSON document: \n" + json.dumps(tattle_props, sort_keys=True, indent=4))
    except Exception:
        logger.exception("Post-processing exception")
    finally:
        if rec_tmp_file_path:
            os.remove(rec_tmp_file_path)
        if props_tmp_file_path:
            os.remove(props_tmp_file_path)
        if transcript_tmp_file_path:
            os.remove(transcript_tmp_file_path)

def upload_props_to_s3(tattle_props, props_filename, props_tmp_file_path, s3_bucket):
    with open(props_tmp_file_path, 'w') as out_file:
        out_file.write(json.dumps(tattle_props, sort_keys=True, indent=4))

    logger.info("Uploading tattle summary JSON document to S3: " + props_filename)

    upload_to_s3(props_filename, props_tmp_file_path, s3_bucket)

def upload_to_s3(upload_filename, local_file_path, s3_bucket):
    try:
        logger.info("Uploading file to S3")

        s3_upload_start = time.time()

        s3_client = boto3.client('s3')
        s3UploadRsp = s3_client.upload_file(local_file_path, s3_bucket, upload_filename)
        ##s3UploadRsp = s3_client.upload_file(local_file_path, s3_bucket, upload_filename, ExtraArgs={'ACL': 'public-read'})

        logger.info("S3 upload response: " + str(s3UploadRsp))
        s3_upload_elapsed = time.time() - s3_upload_start
        logger.info("Uploaded file to S3 in "
            + str(round(s3_upload_elapsed, 2))
            + " seconds"
        )

        s3_url = "https://" + s3_bucket + ".s3.amazonaws.com/" + upload_filename

        logger.info("S3 URL: " + s3_url)
        return s3_url
    except botocore.exceptions.ClientError as ce:
        logger.exception("AWS S3 upload error (ClientError)")
    except Exception:
        logger.exception("AWS S3 upload error (Generic)")

def get_s3_presigned_url(filename, s3_bucket):
    try:
        logger.info("Fetching S3 presigned URL for: " + filename)

        s3_start = time.time()

        s3_client = boto3.client('s3')
        s3PresignedUrlRsp = s3_client.generate_presigned_url('get_object', Params={'Bucket': s3_bucket, 'Key': filename}, ExpiresIn=604800)

        logger.info("S3 presigned URL response: " + str(s3PresignedUrlRsp))
        s3_elapsed = time.time() - s3_start
        logger.info("S3 presigned URL retrieved in "
            + str(round(s3_elapsed, 2))
            + " seconds"
        )

        return s3PresignedUrlRsp
    except botocore.exceptions.ClientError as ce:
        logger.exception("AWS S3 upload error (ClientError)")
    except Exception:
        logger.exception("AWS S3 upload error (Generic)")

def transcribe_recording(transcript_name, transcript_file_path, s3_url, s3_bucket, tattle_props):
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
            OutputBucketName=s3_bucket
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
            s3DownloadRsp = s3_client.download_file(s3_bucket, s3_transcript_filename, transcript_file_path)

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

def analyze_text(tattle_props, transcript, aws_comprehend_region):
    if not transcript:
        return False
        
    transcript = transcript.strip()
        
    if len(transcript) == 0:
        return False

    if aws_comprehend_region == None or len(aws_comprehend_region.strip()) == 0:
        logger.info("Skipping sentiment analysis as no AWS region has been configured")
        return False

    logger.info("Starting text analysis...")
    updated_props = False

    comprehend = boto3.client(service_name='comprehend', region_name=aws_comprehend_region)

    ##Sentiment analysis
    if cfg["text_analysis"]["sentiment"]:
        s3_analysis_start = time.time()

        sentiment_rsp = comprehend.detect_sentiment(Text=transcript, LanguageCode='en')

        s3_analysis_elapsed = time.time() - s3_analysis_start
        logger.info("Sentiment analysis completed in "
            + str(round(s3_analysis_elapsed, 2))
            + " seconds"
        )

        logger.info("Sentiment response:\n" + str(sentiment_rsp))

        if sentiment_rsp["ResponseMetadata"]["HTTPStatusCode"] == 200:
            tattle_props['sentiment'] = sentiment_rsp['Sentiment']
            updated_props = True

    ##Key phrase analysis
    if cfg["text_analysis"]["key_phrases"]:
        s3_analysis_start = time.time()

        key_phrases_rsp = comprehend.detect_key_phrases(Text=transcript, LanguageCode='en')

        s3_analysis_elapsed = time.time() - s3_analysis_start
        logger.info("Key phrase analysis completed in "
            + str(round(s3_analysis_elapsed, 2))
            + " seconds"
        )

        logger.info("Key phrases response:\n" + str(key_phrases_rsp))

        if key_phrases_rsp["ResponseMetadata"]["HTTPStatusCode"] == 200 and 'KeyPhrases' in key_phrases_rsp:
            for phrase_obj in key_phrases_rsp['KeyPhrases']:
                phrase = phrase_obj['Text']
                if phrase and len(phrase) > 0 and not phrase in tattle_props['key_phrases']:
                    tattle_props['key_phrases'].append(phrase)
                    updated_props = True

    return updated_props

def send_slack_msg(tattle_props):
    slack_cfg = cfg["slack"]
    slack_webhook_url = slack_cfg["webhook_url"]
    slack_channel = slack_cfg["channel"]
    slack_username = slack_cfg["username"]
    slack_icon_url = slack_cfg["icon_url"]
    slack_icon_emoji = slack_cfg["icon_emoji"]

    tattle_id = tattle_props["id"]
    tattle_timestamp = tattle_props["timestamp"]
    tattle_recording_url = tattle_props["rec_url"]
    tattle_recording_public_url = tattle_props["rec_public_url"]
    tattle_recording_duration = tattle_props["rec_duration"]
    tattle_transcript = tattle_props["transcript"]
    tattle_sentiment = tattle_props["sentiment"]
    tattle_key_phrases = tattle_props["key_phrases"]

    #good, warning, danger
    color = "good"
    if tattle_sentiment:
        if tattle_sentiment == "MIXED":
            tattle_sentiment = "Mixed"
            color = "warning"
        elif tattle_sentiment == "POSITIVE":
            tattle_sentiment = "Positive"
            color = "green"
        elif tattle_sentiment == "NEUTRAL":
            tattle_sentiment = "Neutral"
            color = "green"
        elif tattle_sentiment == "NEGATIVE":
            tattle_sentiment = "Negative"
            color = "danger"

    attachments = [{}]
    attachment = attachments[0]

    attachment["mrkdwn_in"] = ["text", "pretext"]
    attachment["pretext"] = ":heavy_minus_sign: New " + str(int(round(tattle_recording_duration))) + "s tattle @ " + tattle_timestamp
    attachment["fallback"] = attachment["pretext"]
    attachment["color"] = color

    text_arr = []

    url_link = "<" + tattle_recording_url + "|Private link (No expiration)>"
    if tattle_recording_public_url and len(tattle_recording_public_url) > 0:
        url_link = url_link + "  -  " + "<" + tattle_recording_public_url + "|Public link (7 day expiration)>"
    text_arr.append(url_link)

    if tattle_sentiment and len(tattle_sentiment) > 0:
        text_arr.append("*Sentiment* " + tattle_sentiment)

    if tattle_key_phrases and len(tattle_key_phrases) > 0:
        text_arr.append("*Key Phrases* " + ", ".join(tattle_key_phrases))

    if tattle_transcript and len(tattle_transcript) > 0:
        if len(tattle_transcript) > 2000:
            tattle_transcript = tattle_transcript[0:2000]
        text_arr.append("*Transcript* " + tattle_transcript)

    if not text_arr == None and len(text_arr) > 0:
        text = "\n".join(text_arr)

    attachment["text"] = text
    #attachment["footer"] = "My footer"

    attachments_json = json.dumps(attachments, sort_keys=True, indent=4)

    slack_msg = {}

    if not slack_channel == None and len(slack_channel) > 0:
        slack_msg["channel"] = slack_channel
    if not slack_icon_url == None and len(slack_icon_url) > 0:
        slack_msg["icon_url"] = slack_icon_url
    if not slack_icon_emoji == None and len(slack_icon_emoji) > 0:
        slack_msg["icon_emoji"] = slack_icon_emoji
    if not slack_username == None and len(slack_username) > 0:
        slack_msg["username"] = slack_username

    slack_msg["attachments"] = attachments
    logger.info("Slack WebHook postMessage json:\n" + json.dumps(slack_msg, sort_keys=True, indent=4))

    try:
        webHook = IncomingWebhook(slack_webhook_url)
        webHookRsp = webHook.post(slack_msg)
        logger.info("Slack WebHook postMessage response: " + webHookRsp.text)

        if not webHookRsp.ok:
            logger.error("Slack WebHook message send failed: " + webHookRsp.text)
    except Exception as e:
        logger.exception("Slack WebHook message send error: " + str(e))

	
if __name__ == '__main__':
    try:
	main()
    except KeyboardInterrupt, e:
        logging.info("Stopping...")
    finally:
        GPIO.cleanup() # cleanup all GPIO

    logging.info("Stopped")
