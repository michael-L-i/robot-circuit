import {LiveLoop} from './live-loop.mjs';
import {WorkbenchVoice} from './speech.mjs';
const $ = id => document.getElementById(id);
const labels = {resistor_a:'Resistor · lead 1',resistor_b:'Resistor · lead 2',led_anode:'LED · anode (+)',led_cathode:'LED · cathode (−)',positive:'Positive supply · terminal hole',ground:'Ground · terminal hole'};
let starting = false, cameraGeneration = 0;
let stream = null, imageReady = false, busy = false, modelReady = false, revision = 0, lastFrameTime = null, completed = 0;
let phoneMode=false, phoneSequence=0, latestSpoken='';
const voice=new WorkbenchVoice($('speechAudio'),text=>{$('voiceState').textContent=text;});
const sampler = document.createElement('canvas');
const loop = new LiveLoop(inspectLive);
for (const [key, label] of Object.entries(labels)) {
  const el=document.createElement('label'); el.textContent=label;
  const input=document.createElement('input'); input.type='text'; input.id=key; input.placeholder='Unknown'; input.maxLength=3; input.autocomplete='off';
  input.addEventListener('input',()=>{revision++;invalidate();}); el.append(input); $('fields').append(el);
}
function invalidate() {$('confirmed').checked=false;$('check').disabled=true;$('result').replaceChildren();}
function clearObservations() {revision++;lastFrameTime=null;latestSpoken='';$('replay').disabled=true;$('ledState').hidden=true;for(const key of Object.keys(labels)) $(key).value='';invalidate();$('observation').hidden=true;$('exampleNote').hidden=true;$('freshness').textContent='No analyzed frame yet';}
function controls() {
  $('detailed').disabled=busy;
  $('camera').disabled=starting||!!stream||busy;
  $('stop').disabled=!stream&&!starting&&!phoneMode;
  $('pause').disabled=(!stream&&!phoneMode)||!modelReady;
  $('pause').textContent=loop.enabled?'Pause analysis to review':'Resume live analysis';
  $('analyze').disabled=!imageReady||busy||!modelReady||loop.enabled;
  for(const id of ['upload','example','confirmed',...Object.keys(labels)]) $(id).disabled=busy||loop.enabled;
  $('check').disabled=busy||loop.enabled||!$('confirmed').checked;
  $('cameraState').textContent=phoneMode?(loop.enabled?'iPhone · waiting for new photos':'iPhone · analysis paused'):stream?(loop.enabled?'Live · automatic inspection':'Live · analysis paused'):'Camera off';
  $('phone').disabled=busy||starting;
  $('phone').textContent=phoneMode?'iPhone camera selected':'Use iPhone camera';
}
function message(text) {$('message').textContent=text;}
async function health(){try{const r=await fetch('/api/health');const d=await r.json();modelReady=d.model_present;$('runtime').textContent=d.model_present?`● LOCAL · ${d.model.replace(/\.litertlm$/, '')} / ${d.backend.toUpperCase()}`:'Model download required';controls();}catch{message('Local server is unavailable. Restart it from the terminal.');}}
function stopCamera(){cameraGeneration++;starting=false;loop.stop();voice.stop();phoneMode=false;revision++;if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;$('video').srcObject=null;$('video').hidden=true;$('placeholder').hidden=imageReady;controls();}
$('camera').onclick=async()=>{if(starting)return;let attempt;try{stopCamera();attempt=cameraGeneration;starting=true;message('Opening camera… Allow camera access if your browser or macOS asks.');controls();const incoming=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1920},height:{ideal:1080}},audio:false});if(attempt!==cameraGeneration){incoming.getTracks().forEach(t=>t.stop());return;}stream=incoming;starting=false;$('video').srcObject=stream;await $('video').play();$('video').hidden=false;$('frame').hidden=true;$('placeholder').hidden=true;imageReady=false;completed=0;clearObservations();if(modelReady){message('Camera ready — position your board. First photo in 2 seconds…');loop.start(2000);}else message('Camera is live. Waiting for the model; use Resume live analysis when ready.');controls();}catch(e){if(attempt!==cameraGeneration)return;stopCamera();message(`Camera unavailable: ${e.message}. Allow browser camera access in macOS Settings, or upload a photo.`);}};
$('stop').onclick=()=>{stopCamera();clearObservations();message('Camera stopped.');};
$('pause').onclick=()=>{revision++;if(loop.enabled){loop.stop();message('Analysis paused; video stays live. Review the last observations. An in-flight result will be discarded.');}else{clearObservations();loop.start();}controls();};
function encodeFrame(source,w,h,canvas=sampler){const ratio=Math.min(1,1600/Math.max(w,h));canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);canvas.getContext('2d').drawImage(source,0,0,canvas.width,canvas.height);return canvas.toDataURL('image/jpeg',.95);}
$('upload').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const bitmap=await createImageBitmap(f);if(bitmap.width*bitmap.height>16000000){bitmap.close();throw Error('Use a photo under 16 megapixels.');}stopCamera();clearObservations();encodeFrame(bitmap,bitmap.width,bitmap.height,$('frame'));bitmap.close();$('frame').hidden=false;$('placeholder').hidden=true;imageReady=true;message('Photo loaded. Click Inspect photo.');controls();}catch(err){message(err.message);}e.target.value='';};
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;}
function renderResult(d, tentative=false){$('result').replaceChildren();const h=document.createElement('h3');h.textContent=(tentative?'Unverified · ':'')+({connected:'Series path connected',correction:'Suggested correction',invalid:'Resolve wiring first',needs_observation:'Partial observations',no_circuit:'No circuit identified'}[d.status]);const p=document.createElement('p');p.textContent=d.summary;$('result').append(h,p);for(const finding of d.findings||[]){const item=document.createElement('p');item.textContent=finding;$('result').append(item);}for(const move of d.moves){const div=document.createElement('div');div.className='move';div.textContent=`${labels[move.lead]}: ${move.from_hole.toUpperCase()} → ${move.to_hole.toUpperCase()} — ${move.reason}`;$('result').append(div);}if(d.alternatives?.length){const alt=document.createElement('p');alt.textContent='Other equally short repairs exist. This option favors moving flexible jumpers before component leads.';$('result').append(alt);}if(tentative){const note=document.createElement('p');note.textContent='Based on the last analyzed frame, not the current video. Pause analysis to verify pins before moving parts.';$('result').append(note);}}
async function inspectImage(image,isCurrent,capturedAt){
  busy=true;controls();
  const start=Date.now();message('Inspecting the latest frame locally…');
  const timer=setInterval(()=>{if(isCurrent())message(`Gemma inspecting… ${Math.round((Date.now()-start)/1000)}s. Video continues live.`);},1000);
  try{
    const d=await post('/api/analyze',{image,detailed:$('detailed').checked});
    if(!isCurrent())return;
    const diagnosis=d.circuit_present===false?{status:'no_circuit',summary:'Gemma did not identify a circuit in this frame. See the visual observations and suggested camera adjustment.',moves:[]}:await post('/api/check',d.pins);
    if(!isCurrent())return;
    invalidate();for(const key of Object.keys(labels))$(key).value=d.pins[key]||'';
    $('observation').textContent=[d.summary,d.visual_analysis,...Object.entries(d.pin_evidence||{}).map(([key,value])=>`${labels[key]}: ${value}`),...d.uncertainties.map(x=>'Uncertain: '+x),d.next_view?`Next detail to check: ${d.next_view}`:''].filter(Boolean).join('\n\n');$('observation').hidden=false;
    $('ledState').hidden=false;$('ledState').textContent='LED · '+({lit:'Appears lit',unlit:'Appears unlit',not_visible:'Not visible',uncertain:'Cannot determine from this photo'}[d.led_state]||'Cannot determine from this photo');
    latestSpoken=d.spoken_feedback||[d.summary,d.visual_analysis,d.next_view].filter(Boolean).join(' ').slice(0,1200);
    $('replay').disabled=false;
    if(voice.enabled){$('speechAudio').hidden=false;void voice.say(latestSpoken);}
    lastFrameTime=capturedAt;completed++;renderResult(diagnosis,true);
    message(`Inspection ${completed} complete · ${d.seconds}s inference. ${loop.enabled?'Next: newest camera frame.':'Review the proposed holes.'}`);
  }catch(err){if(isCurrent()){loop.stop();invalidate();message(`Analysis paused: ${err.message}. Resume to retry.`);}}
  finally{clearInterval(timer);busy=false;controls();}
}
async function inspectLive(isCurrent){
  if(phoneMode){
    if(!modelReady)return;
    const response=await fetch(`/api/phone/latest?after=${phoneSequence}`,{cache:'no-store'});
    if(response.status===204)return;
    if(!response.ok){loop.stop();message('Open this dashboard at http://127.0.0.1:8000 on your Mac to receive phone photos.');controls();return;}
    const frame=await response.json();if(!isCurrent())return;
    const image=new Image();image.src=frame.image;await image.decode();if(!isCurrent())return;
    encodeFrame(image,image.naturalWidth,image.naturalHeight,$('frame'));
    $('frame').hidden=false;$('placeholder').hidden=true;imageReady=true;
    $('phoneState').textContent=`Photo ${frame.sequence} received · ${new Date(frame.received_at*1000).toLocaleTimeString()}`;
    const before=completed;
    await inspectImage(frame.image,isCurrent,frame.received_at*1000);
    if(completed>before)phoneSequence=frame.sequence;
    return;
  }
  if(!stream||!modelReady||!$('video').videoWidth)return;
  const capturedAt=Date.now();
  const image=encodeFrame($('video'),$('video').videoWidth,$('video').videoHeight);
  await inspectImage(image,isCurrent,capturedAt);
}
$('analyze').onclick=async()=>{clearObservations();const version=revision;await inspectImage($('frame').toDataURL('image/jpeg',.95),()=>revision===version,Date.now());};
$('confirmed').onchange=controls;
$('pins').onsubmit=async e=>{e.preventDefault();if(!$('confirmed').checked||loop.enabled)return;const version=revision;try{const pins=Object.fromEntries(Object.keys(labels).map(key=>[key,$(key).value.trim()||null]));const d=await post('/api/check',pins);if(version===revision&&!loop.enabled)renderResult(d);}catch(err){message(err.message);}};
$('example').onclick=()=>{clearObservations();const p={resistor_a:'a5',resistor_b:'a9',led_anode:'c10',led_cathode:'c11',positive:'e5',ground:'e11'};for(const [k,v]of Object.entries(p))$(k).value=v;$('exampleNote').hidden=false;};
window.addEventListener('pagehide',stopCamera);
function usePhone(){stopCamera();clearObservations();phoneMode=true;message('Ready for your iPhone. Scan the QR code and take a circuit photo. New photos are inspected automatically.');if(modelReady)loop.start();controls();}
$('phone').onclick=usePhone;
$('voice').onclick=()=>{
  voice.enabled=!voice.enabled;$('voice').textContent=voice.enabled?'Mute voice':'Enable voice';
  if(voice.enabled){$('speechAudio').hidden=false;void voice.say(latestSpoken||'Circuit Lab is ready. Send a photo from your iPhone, and I will describe what I can see.',true);}
  else{voice.stop();$('voiceState').textContent='Voice muted';}
};
$('replay').onclick=()=>{$('speechAudio').hidden=false;void voice.say(latestSpoken,true);};
async function setupPhone(){try{const response=await fetch('/api/phone/info');if(!response.ok)throw Error('Open the Mac dashboard at http://127.0.0.1:8000');const data=await response.json();$('phoneUrl').textContent=data.url;$('phoneUrl').href=data.url;await health();usePhone();}catch(error){$('phoneState').textContent=error.message;}}
setupPhone();
health();setInterval(()=>{if(!modelReady)health();if(lastFrameTime)$('freshness').textContent=`Last analyzed frame: ${Math.round((Date.now()-lastFrameTime)/1000)}s ago · ${new Date(lastFrameTime).toLocaleTimeString()}`;},1000);
