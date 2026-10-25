"""Explicit remote runtime selection; never fall back between engines."""
import base64
import os
from pathlib import Path
from .ollama import OllamaClient
from .litert_remote import LiteRTClient


def make_client(runtime=None):
    runtime=runtime or os.getenv('CIRCUIT_REMOTE_RUNTIME',os.getenv('CIRCUIT_INFERENCE','ollama'))
    if runtime in ('local','ollama'):return OllamaClient()
    if runtime=='litert':return LiteRTClient()
    raise ValueError(f'Unknown remote runtime: {runtime}')


class RemoteVision:
    def __init__(self,client):self.client=client
    def analyze(self,image_path,detailed=False,simple=False):
        from .inference import LIVE_PROMPT,PROMPT,parse_observation
        image=base64.b64encode(Path(image_path).read_bytes()).decode()
        return parse_observation(self.client.complete(
            [dict(role='user',content=LIVE_PROMPT if simple else PROMPT,images=[image])],structured=True))
