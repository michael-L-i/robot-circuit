import time
import pytest
from ui.serve import analyze_frame

class Client:
    model='test-jetson'
    calls=[]
    def complete(self,messages):
        self.calls.append(messages)
        return 'An observed board.'


def test_exact_frame_used_and_returned():
    client=Client();client.calls=[]
    frame=dict(received_at=time.time(),sequence=17,image='data:image/jpeg;base64,AAAA')
    result=analyze_frame(frame,client)
    assert len(client.calls)==1
    assert client.calls[0][0]['images']==['AAAA']
    assert result['image']==frame['image'] and result['frame_sequence']==17
    assert result['text']=='An observed board.'


def test_stale_camera_never_calls_model():
    client=Client();client.calls=[]
    with pytest.raises(ValueError):
        analyze_frame(dict(received_at=time.time()-40,sequence=1,image='old'),client)
    assert client.calls==[]


def test_missing_camera_never_calls_model():
    client=Client();client.calls=[]
    with pytest.raises(ValueError):analyze_frame(None,client)
    assert client.calls==[]
