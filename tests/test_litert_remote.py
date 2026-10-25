import io
import json
import pytest
from circuit_lab.litert_remote import LiteRTClient


def test_image_is_passed_as_data_url_without_changing_input():
    c=LiteRTClient();messages=[dict(role='user',content='Look',images=['YWJj'])]
    payload=c.payload(messages)
    assert payload['messages'][0]['content'][1]['image_url']['url']=='data:image/jpeg;base64,YWJj'
    assert messages[0]['content']=='Look'
    assert payload['max_tokens']==700 and payload['model']=='gemma4-e4b'


def test_complete_rejects_truncation(monkeypatch):
    c=LiteRTClient()
    monkeypatch.setattr(c,'open',lambda *a,**k:io.BytesIO(json.dumps({'choices':[{'finish_reason':'length','message':{'content':'Partial'}}]}).encode()))
    with pytest.raises(RuntimeError,match='incomplete'):c.complete([])


def test_stream_only_returns_visible_text(monkeypatch):
    c=LiteRTClient()
    raw='data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'private','content':'Visible'}}]})+'\n'
    raw+='data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'stop'}]})+'\ndata: [DONE]\n'
    monkeypatch.setattr(c,'open',lambda *a,**k:io.BytesIO(raw.encode()))
    assert list(c.stream([]))==['Visible']


def test_truncated_stream_fails(monkeypatch):
    c=LiteRTClient();monkeypatch.setattr(c,'open',lambda *a,**k:io.BytesIO(b'data: [DONE]\n'))
    with pytest.raises(RuntimeError,match='without a completed'):list(c.stream([]))
