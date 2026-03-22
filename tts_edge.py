from __future__ import annotations

import io
import logging
import uuid

import numpy as np
from gtts import gTTS
from livekit import rtc
from livekit.agents import tts

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
NUM_CHANNELS = 1


class EdgeTTS(tts.TTS):
    """
    Google TTS wrapper — free, no API key, supports Armenian (hy).
    Class kept as EdgeTTS so agent.py needs no changes.
    """

    def __init__(
        self,
        *,
        voice: str = "hy-AM-AnahitNeural",  # ignored, kept for compatibility
        rate: str = "-5%",                   # ignored, kept for compatibility
        lang: str = "hy",
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._lang = lang

    def synthesize(self, text: str) -> "GTTSStream":
        return GTTSStream(
            tts=self,
            input_text=text,
            conn_options=None,
        )


class GTTSStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: EdgeTTS,
        input_text: str,
        conn_options=None,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)

    async def _run(self) -> None:
        tts_inst: EdgeTTS = self._tts  # type: ignore

        try:
            # Generate MP3 using gTTS
            tts_obj = gTTS(text=self._input_text, lang=tts_inst._lang, slow=False)
            mp3_buffer = io.BytesIO()
            tts_obj.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)
            mp3_data = mp3_buffer.read()

            if not mp3_data:
                logger.warning("gTTS: empty audio received")
                return

            # Decode MP3 to PCM using pydub
            from pydub import AudioSegment

            audio = (
                AudioSegment.from_mp3(io.BytesIO(mp3_data))
                .set_frame_rate(SAMPLE_RATE)
                .set_channels(NUM_CHANNELS)
                .set_sample_width(2)
            )

            pcm = np.frombuffer(audio.raw_data, dtype=np.int16)
            frame_size = SAMPLE_RATE // 10
            request_id = str(uuid.uuid4())
            segment_id = str(uuid.uuid4())

            for i in range(0, len(pcm), frame_size):
                chunk_pcm = pcm[i : i + frame_size]
                frame = rtc.AudioFrame(
                    data=chunk_pcm.tobytes(),
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    samples_per_channel=len(chunk_pcm),
                )
                self._event_ch.send_nowait(
                    tts.SynthesizedAudio(
                        request_id=request_id,
                        segment_id=segment_id,
                        frame=frame,
                    )
                )

        except Exception:
            logger.exception("gTTS synthesis failed")
            raise