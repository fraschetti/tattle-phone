# -*- coding: utf-8 -*-

import pyaudio
import wave
import time

## Adapted from sloria's recorder.py - https://gist.github.com/sloria/5693955
## License - MIT - https://sloria.mit-license.org/

# The MIT License (MIT)
# Copyright © 2019 Steven Loria
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

class SoundRecorder:
    def __init__(self, filename):
        self._pa = pyaudio.PyAudio()
        self.channels = 1
        self.rate = 44100
        self.frames_per_buffer = 256
        self.wavefile = self._prepare_file(filename)
 
        self._stream = None
        self._start_time = None
        self._duration = None

    def __enter__(self):
        return self

    def __exit__(self, exception, value, traceback):
        self.close()

    def start_recording(self):
        self._stream = self._pa.open(format=pyaudio.paInt16,
                                        channels=self.channels,
                                        rate=self.rate,
                                        input=True,
                                        frames_per_buffer=self.frames_per_buffer,
                                        stream_callback=self.get_callback())
        self._start_time = time.time()
        self._stream.start_stream()
        return self

    def stop_recording(self):
        self._stream.stop_stream()
        if self._start_time:
            self._duration = time.time() - self._start_time
        return self

    def get_duration(self):
        if not self._duration == None:
            return self._duration

        if self._stream == None or self._start_time == None:
            return None

        #Return current time delta if still recording
        return time.time() - self._start_time

    def get_callback(self):
        def callback(in_data, frame_count, time_info, status):
            self.wavefile.writeframes(in_data)
            return in_data, pyaudio.paContinue
        return callback
		
    def _prepare_file(self, fname, mode='wb'):
        wavefile = wave.open(fname, mode)
        wavefile.setnchannels(1)
        wavefile.setsampwidth(self._pa.get_sample_size(pyaudio.paInt16))
        wavefile.setframerate(self.rate)
        return wavefile

    def close(self):
        self._stream.close()
        self._stream = None
        self._pa.terminate()
        self._pa = None
        self.wavefile.close()
        self.wavefile = None
