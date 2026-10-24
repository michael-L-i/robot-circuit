"""One shared E4B engine with the existing webcam app; fresh bounded conversations."""
import json
import time
import copy
from circuit_lab.app import vision, lock
from circuit_lab.inference import MODEL, BACKEND, VISION_BACKEND, ROOT

PROMPT = '''You supervise a simulated breadboard repair robot. Select ONE next action.
If a camera image is attached, inspect it alongside the calibrated marker detections.
Marker identities and grasp offsets were explicitly taught; detections may be missing.
Never invent coordinates or claim to recognize an unseen object. Motion code validates target visibility.
The marker-based perception system measures poses; you select the task skill.
The circuit should be supply -> jumper -> copper mesh -> 330 ohm resistor -> red LED -> ground.
The test pad is connected to the mesh/resistor input. A 100k pulldown gives an open input 0V.
The probe's reference lead is permanently grounded. A null voltage is failed probe contact, not zero voltage. A numerical 0.0 reading is VALID zero volts. Before placement it is the expected fault to REPAIR, not a reason to abort.
Pick up the probe, measure, dock it before picking up the misplaced jumper. Place the jumper on the mesh,
then pick up the probe again, measure, dock, and finish ONLY when measured voltage exceeds 4V and LED is lit.
After an unsuccessful repair or invalid measurement, abort with an explanation; do not repeat blindly.
Use only allowed_actions. If the most recent measurement has null voltage and the probe is docked, abort. Do not start a repair. The allowed_actions list is authoritative; never choose an action outside it.
An already working circuit needs no repair. Measurements are simulated, not physical observations.
Return ONLY JSON: {"action":"one allowed action", "reason":"one short sentence grounded in observations"}.
'''

def parse(raw, allowed):
    text = raw.strip()
    if text.startswith('```'):
        text = text.split('\n',1)[1].rsplit('```',1)[0].strip()
    data = json.loads(text)
    if not isinstance(data,dict) or data.get('action') not in allowed or not isinstance(data.get('reason'),str):
        raise ValueError(f'Model returned an invalid decision; allowed: {allowed}. Nothing moved.')
    return dict(action=data['action'], reason=data['reason'][:600])

def decide(observation, events, image_path=None):
    import litert_lm
    if not MODEL.is_file(): raise ValueError(f'Model missing: {MODEL}')
    if vision.engine is None:
        backend = litert_lm.Backend.GPU() if BACKEND == 'gpu' else litert_lm.Backend.CPU()
        vb = litert_lm.Backend.GPU() if VISION_BACKEND == 'gpu' else litert_lm.Backend.CPU()
        vision.engine = litert_lm.Engine(str(MODEL), backend=backend, vision_backend=vb,
            max_num_tokens=8192, cache_dir=str(ROOT/'.cache'))
    start = time.monotonic()
    # Do not recursively feed model-written explanations back as sensor evidence.
    observation=copy.deepcopy(observation)
    if 'perception' in observation:
        observation['perception']={
            'method':'camera ArUco detection with taught IDs',
            'visible_objects':list(observation['perception']['detections']),
            'missing_objects':observation['perception']['missing']}
    observation['targets']={name:[round(float(x),4) for x in pos] for name,pos in observation.get('targets',{}).items()}
    history=[{key:event[key] for key in ('action','note','ok') if key in event} for event in events[-4:]]
    retries=0
    with vision.engine.create_conversation(
        thinking_config=litert_lm.ThinkingConfig(enable_thinking=False, thinking_token_budget=0),
        sampler_config=litert_lm.SamplerConfig(temperature=0.1), max_output_tokens=180) as conv:
        text = PROMPT+'\n'+json.dumps(dict(observation=observation, recent_events=history))
        message = text if image_path is None else {'role':'user','content':[{'type':'image','path':str(image_path)},{'type':'text','text':text}]}
        raw = str(conv.send_message(message))
        try:
            decision = parse(raw, observation['allowed_actions'])
        except (ValueError, TypeError):
            retries=1
            raw = str(conv.send_message('Your response was rejected. Return exactly one JSON object with action and reason. The ONLY permitted actions now are: '+json.dumps(observation['allowed_actions'])+'. Current sensor readings: '+json.dumps(observation['measurements'])+'. Numerical 0V before repair is a valid measurement of the open circuit; it is not failed probe contact.'))
            decision = parse(raw, observation['allowed_actions'])
    return dict(**decision, model=MODEL.name,
                seconds=round(time.monotonic()-start,2), source='local Gemma E4B', image_observed=image_path is not None, formatting_retries=retries)
