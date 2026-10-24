"""One shared E4B engine with the existing webcam app; fresh bounded conversations."""
import json
import time
import copy
from circuit_lab.app import vision, lock
from circuit_lab.inference import MODEL, BACKEND, VISION_BACKEND, ROOT
from arm_sim.planner import parse

PROMPT = '''You supervise a simulated resistor replacement robot. Select ONE next action.
Inspect the attached camera image alongside calibrated marker detections. Marker identities
and grasp offsets are taught; missing detections are not evidence of an unseen object's pose.
Circuit: Arduino 5V -> TP1 input pad -> resistor socket -> TP2 output pad (LED anode)
-> red LED -> GND. A 100k pulldown on TP2 defines 0V for an open resistor.
The probe reference is permanently grounded. Null voltage means failed probe contact,
NEVER zero volts. Numerical 0V with valid contact is a valid reading.
Pick the probe and measure TP1/input, then TP2/output. TP1 5V + TP2 0V with LED dark
means the resistor is open: dock the probe, remove_resistor, discard_resistor, pick_spare,
insert_resistor, pick_probe, and measure_output again.
TP1 0V means a supply problem: do NOT replace the resistor; dock and abort.
After replacement TP2 approximately 2V with LED lit verifies repair: dock and finish.
After replacement still 0V means the spare failed: dock and abort, never replace again.
An already healthy circuit (TP1 5V, TP2 approximately 2V, LED lit) needs no replacement;
dock and finish. Failed contact means dock and abort, not an open-resistor diagnosis.
The allowed_actions list is authoritative. Choose only an action in it.
Never feed previous explanations into your diagnosis; use measured sensor facts.
Measurements and images are simulated, not physical hardware observations.
Return ONLY JSON: {"action":"one allowed action", "reason":"one short sentence grounded in observations"}.
'''

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
            raw = str(conv.send_message('Your response was rejected. Return exactly one JSON object with action and reason. The ONLY permitted actions now are: '+json.dumps(observation['allowed_actions'])+'. Current sensor readings: '+json.dumps(observation['measurements'])+'. Null is failed contact; numeric zero is valid. Diagnose using the measurement point and whether replacement already happened.'))
            decision = parse(raw, observation['allowed_actions'])
    return dict(**decision, model=MODEL.name,
                seconds=round(time.monotonic()-start,2), source='local Gemma E4B', image_observed=image_path is not None, formatting_retries=retries)
