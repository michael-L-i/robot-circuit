import copy
from arm_sim import planner


def test_model_history_uses_sensor_facts_not_previous_model_explanations(monkeypatch,tmp_path):
    messages=[]
    class Conversation:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def send_message(self,message):
            messages.append(message)
            return '{"action":"pick_probe","reason":"Begin measurement"}'
    class Engine:
        def create_conversation(self,**kwargs):return Conversation()
    model=tmp_path/'fake.litertlm';model.write_text('mock')
    monkeypatch.setattr(planner,'MODEL',model)
    monkeypatch.setattr(planner.vision,'engine',Engine())
    observation=dict(targets={'probe':[.2,-.15,.06]},measurements=[],allowed_actions=['pick_probe','abort'],
        perception=dict(detections={'probe':{'base_from_marker':'PRIVATE_MATRIX'}},missing=[]))
    original=copy.deepcopy(observation)
    result=planner.decide(observation,[dict(action='measure',note='Probe reads 0.00 V',ok=True,
        decision={'reason':'UNTRUSTED_OLD_MODEL_EXPLANATION'})])
    assert result['action']=='pick_probe'
    assert 'UNTRUSTED_OLD_MODEL_EXPLANATION' not in messages[0]
    assert 'PRIVATE_MATRIX' not in messages[0]
    assert 'Probe reads 0.00 V' in messages[0]
    assert observation==original
