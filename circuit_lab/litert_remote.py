"""LiteRT-LM's OpenAI-compatible server over a private Jetson SSH tunnel.

No Ollama calls or silent runtime fallback. Uses only standard-library HTTP.
"""
import json
import os
import urllib.error
import urllib.request


class LiteRTClient:
    runtime = 'LiteRT-LM'

    def __init__(self, url=None, model=None):
        self.url=(url or os.getenv('CIRCUIT_LITERT_URL','http://127.0.0.1:11436')).rstrip('/')
        self.model=model or os.getenv('CIRCUIT_LITERT_MODEL','gemma4-e4b')

    def open(self,path,payload=None,timeout=180):
        request=urllib.request.Request(self.url+path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Content-Type':'application/json'})
        try:return urllib.request.urlopen(request,timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail=exc.read(2000).decode(errors='replace')
            raise RuntimeError(f'LiteRT-LM returned HTTP {exc.code}: {detail}') from exc
        except OSError as exc:
            raise RuntimeError('Cannot reach Jetson LiteRT-LM. Check its service and SSH tunnel.') from exc

    def status(self):
        with self.open('/v1/models',timeout=5) as response:models=json.load(response).get('data',[])
        return dict(reachable=True,model_present=any(m['id']==self.model for m in models),
                    model=self.model,runtime=self.runtime)

    def payload(self,messages,stream=False,structured=False):
        converted=[]
        for message in messages:
            item=dict(role=message['role'],content=message.get('content',''))
            if message.get('images'):
                item['content']=[{'type':'text','text':item['content']}]+[
                    {'type':'image_url','image_url':{'url':image if image.startswith('data:') else 'data:image/jpeg;base64,'+image}}
                    for image in message['images']]
            converted.append(item)
        if structured:
            converted=[{'role':'system','content':'Return only the requested JSON object, without markdown fences.'}]+converted
        return dict(model=self.model,messages=converted,stream=stream,max_tokens=700,temperature=.1)

    def complete(self,messages,structured=False):
        with self.open('/v1/chat/completions',self.payload(messages,structured=structured)) as r:
            result=json.load(r)
        choice=result['choices'][0]
        if choice.get('finish_reason')!='stop':raise RuntimeError('LiteRT-LM response was incomplete; no completed analysis available.')
        text=choice['message'].get('content')
        if not isinstance(text,str) or not text.strip():raise RuntimeError('LiteRT-LM returned no answer.')
        return text

    def stream(self,messages):
        finished=False
        with self.open('/v1/chat/completions',self.payload(messages,stream=True)) as response:
            for line in response:
                line=line.decode().strip()
                if not line.startswith('data:'):continue
                data=line[5:].strip()
                if data=='[DONE]':
                    if not finished:raise RuntimeError('LiteRT-LM stream ended without a completed answer.')
                    return
                event=json.loads(data)
                if event.get('error'):raise RuntimeError(str(event['error']))
                for choice in event.get('choices',[]):
                    content=choice.get('delta',{}).get('content')
                    if content:yield content
                    reason=choice.get('finish_reason')
                    if reason:
                        if reason!='stop':raise RuntimeError('LiteRT-LM response reached its limit or stopped unexpectedly.')
                        finished=True
        if not finished:raise RuntimeError('LiteRT-LM connection ended before the answer completed.')
