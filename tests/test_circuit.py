import pytest
import json
import base64
import io
from PIL import Image
from fastapi.testclient import TestClient
from circuit_lab.circuit import Pins, inspect, net
from circuit_lab.inference import parse_observation
from circuit_lab.app import app

BASE = dict(resistor_a='a5', resistor_b='a9', led_anode='c10', led_cathode='c11', positive='e5', ground='e11')

def test_move_repairs_series_path():
    p=BASE.copy()
    result=inspect(Pins(**p))
    assert result['moves'][0]['from_hole']=='a9'
    assert result['moves'][0]['to_hole']=='a10'
    for m in result['moves']: p[m['lead']]=m['to_hole']
    assert inspect(Pins(**p))['status']=='connected'

def test_equivalent_holes_and_nonpolar_resistor():
    p={**BASE,'resistor_a':'b10','resistor_b':'d5'}
    assert inspect(Pins(**p))['status']=='connected'
    assert net('a5')==net('e5') and net('e5')!=net('f5')

def test_unknown_does_not_move():
    assert inspect(Pins(**{**BASE,'led_anode':None}))['moves']==[]

def test_duplicate_holes_require_review():
    assert inspect(Pins(**{**BASE,'led_anode':'e5'}))['moves']==[]

def test_short_is_identified_and_plan_repairs_it():
    p={**BASE,'ground':'d5'}
    result=inspect(Pins(**p))
    assert 'short' in result['findings'][0]
    for move in result['moves']: p[move['lead']]=move['to_hole']
    assert inspect(Pins(**p))['status']=='connected'

def test_bad_model_response_is_not_a_diagnosis():
    for raw in ('nonsense','{"pins":{"resistor_a":"a999"}}'):
        assert parse_observation(raw)['pins']['resistor_a'] is None

def test_fenced_model_response():
    assert parse_observation('```json\n{"pins":{"resistor_a":"A5"},"summary":"Look","uncertainties":[]}\n```')['pins']['resistor_a']=='a5'

def test_api_validation():
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        assert client.post('/api/check',json={'positive':'rail+'}).status_code==422
        assert client.post('/api/check',json=BASE).json()['moves'][0]['to_hole']=='a10'

@pytest.mark.parametrize('detailed', [False, True])
def test_image_inference_contract(monkeypatch,tmp_path,detailed):
    import circuit_lab.app as module
    model=tmp_path/'model.litertlm';model.touch()
    monkeypatch.setattr(module,'MODEL',model)
    def fake(path, **options):
        assert options['detailed'] is detailed
        assert Image.open(path).size==(30,30)
        return {'pins':BASE,'summary':'test observation','uncertainties':[]}
    monkeypatch.setattr(module.vision,'analyze',fake)
    buf=io.BytesIO();Image.new('RGB',(30,30)).save(buf,format='PNG')
    with TestClient(app) as client:
        r=client.post('/api/analyze',json={'image':base64.b64encode(buf.getvalue()).decode(),'detailed':detailed})
        assert r.status_code==200 and r.json()['requires_review']
        assert client.post('/api/analyze',json={'image':'bad'}).status_code==400


@pytest.mark.parametrize('offset', [0, 17, 40])
@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('broken', ['positive', 'ground'])
def test_misplaced_jumper_is_derived_at_different_locations(offset, side, broken):
    p={**BASE, 'resistor_b':'a10'}
    p[broken] = 'e7' if broken=='positive' else 'e13'
    p={k:chr(ord(h[0])+(5 if side=='right' else 0))+str(int(h[1:])+offset) for k,h in p.items()}
    result=inspect(Pins(**p))
    assert len(result['moves']) == 1
    move=result['moves'][0]
    assert move['lead']==broken and move['component']=='jumper'
    p[broken]=move['to_hole']
    assert net(p['positive'])==net(p['resistor_a'])
    assert net(p['resistor_b'])==net(p['led_anode'])
    assert net(p['led_cathode'])==net(p['ground'])
    assert len({net(p[k]) for k in ('positive','led_anode','ground')})==3


def test_resistor_after_led_is_valid():
    p=dict(positive='a5',led_anode='b5',led_cathode='c7',resistor_a='d7',resistor_b='d9',ground='e9')
    assert inspect(Pins(**p))['status']=='connected'


def test_partial_observations_are_useful_without_guessing_move():
    result=inspect(Pins(**{**BASE,'led_anode':None}))
    assert result['status']=='needs_observation'
    assert result['findings'] and result['missing']==['led_anode']
    assert result['moves']==[]


def test_bad_endpoint_preserves_other_findings():
    result=parse_observation(json.dumps(dict(pins={**BASE,'positive':'rail+'},summary='A jumper appears disconnected.',visual_analysis='The red wire ends next to the resistor strip.',uncertainties=[])))
    assert result['pins']['positive'] is None
    assert result['pins']['resistor_a']=='a5'
    assert result['visual_analysis'].startswith('The red wire')
    assert result['uncertainties']


def test_no_circuit_cannot_produce_pin_plan():
    result=parse_observation(json.dumps(dict(pins=BASE,circuit_present=False,summary='Blank image',uncertainties=[])))
    assert all(v is None for v in result['pins'].values())
