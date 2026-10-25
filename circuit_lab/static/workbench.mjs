import {readEvents} from './ndjson.mjs';
const $ = id => document.getElementById(id);
let state = {}, pairingUrl = '', sequence = 0, busy = false, history = [], lastReply = '', feedNodes = new Map();
async function json(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (!response.ok) { const error = await response.json(); throw Error(error.detail || 'Request failed'); }
  return response.json();
}
async function refresh() {
  try {
    const [next, info] = await Promise.all([json('/api/live/state'), json('/api/phone/info')]); state = next;
    if (pairingUrl !== info.url) { pairingUrl = info.url; $('link').textContent = pairingUrl; $('link').href = pairingUrl; $('qr').src = '/api/phone/qr?t='+Date.now(); }
    const age = state.received_at ? Math.max(0,Math.round(Date.now()/1000-state.received_at)) : null;
    $('camera').textContent = age === null ? 'Waiting for phone' : age > 30 ? `Last frame ${age}s ago · stale` : `Connected · frame ${age}s ago`;
    $('status').textContent = state.paused ? 'Inspection paused' : ({waiting:'Waiting for camera',inspecting:'Gemma inspecting…',ready:'Inspection ready',speaking:'Speaking on the Mac…',error:'Inspection needs attention'}[state.phase] || state.phase);
    $('details').textContent = `${state.received_sequence} frames received · ${state.processed} inspected` + (state.seconds ? ` · ${state.seconds}s inference` : '');
    $('pause').textContent = state.paused ? 'Resume inspection' : 'Pause inspection';
    $('mute').textContent = state.voice ? 'Mute voice' : 'Enable voice';
    $('error').textContent = state.error || (!state.running ? 'Automatic inspection is off. Start the workbench launcher.' : '');
    if (state.demo && state.demo_step) $('status').textContent = 'Robot demo · ' + state.demo_step;
    for (const item of state.feed || []) {            // Gemma's live commentary on each robot step
      let node = feedNodes.get(item.t);
      if (!node) { node = bubble('assistant'); node.parentElement.querySelector('strong').textContent = 'Gemma · ' + item.step; feedNodes.set(item.t, node); }
      const text = item.text || (item.done ? '' : '…');
      if (node.textContent !== text) { node.textContent = text; $('conversation').scrollTop = $('conversation').scrollHeight; }
    }
    if (state.summary) { $('result').hidden = false; $('led').textContent = 'LED: '+state.led_state.replaceAll('_',' '); $('finding').textContent = state.spoken_feedback || state.summary; }
    if (state.received_sequence > sequence) {
      const response = await fetch('/api/phone/latest?after='+sequence);
      if (response.ok && response.status !== 204) { const frame = await response.json(); sequence=frame.sequence; $('preview').src=frame.image; $('preview').hidden=false; }
    }
  } catch(error) { $('error').textContent=error.message; }
}
async function connections() {
  try { const info=await json('/api/system');
    $('jetson').textContent = info.inference.reachable ? info.inference.model_present ? `${info.inference.model} · ready` : 'Connected · model missing' : 'Disconnected · check launcher';
    $('routing').textContent = info.inspection_provider === 'ollama' ? 'Images → Jetson Gemma · spoken findings → Mac speakers' : 'Camera inspection uses the local Mac model. Chat requires the Jetson tunnel.';
  } catch(error) { $('jetson').textContent=error.message; }
}
async function setting(body) { await json('/api/live/settings',body); await refresh(); }
$('pause').onclick=()=>setting({paused:!state.paused}).catch(e=>$('error').textContent=e.message);
$('mute').onclick=()=>setting({voice:!state.voice}).catch(e=>$('error').textContent=e.message);
function bubble(role,text='') {
  $('conversation').querySelector('.empty')?.remove();
  const node=document.createElement('div'); node.className='message';
  const label=document.createElement('strong');label.textContent=role==='user'?'You':'Gemma';
  const content=document.createElement('span');content.textContent=text;node.append(label,content);$('conversation').append(node);
  while($('conversation').children.length>24)$('conversation').firstElementChild.remove();
  return content;
}
async function say(text) {
  if (!state.voice) return;
  $('chat-status').textContent='Preparing voice on your Mac…';
  const result=await json('/api/speaker/play',{text:text.slice(0,1500)});
  $('chat-status').textContent=result.played?'Reply played on your Mac.':'Voice muted.';
}
$('replay').onclick=()=>say(lastReply).catch(e=>$('chat-status').textContent=e.message);
$('chat').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const prompt=$('question').value.trim();if(!prompt)return;
  busy=true;$('send').disabled=true;$('replay').hidden=true;
  let answer='', complete=false, output;
  try {
    await setting({paused:true});
    bubble('user',prompt);output=bubble('assistant');$('chat-status').textContent='Waiting for Jetson…';
    const response=await fetch('/api/assistant/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,history:history.slice(-12),use_camera:$('use-camera').checked})});
    if(!response.ok){const data=await response.json();throw Error(data.detail||'Chat failed');}
    for await (const item of readEvents(response.body)) {
      if(item.type==='error')throw Error(item.message);
      if(item.type==='text'){answer+=item.text;output.textContent=answer;$('chat-status').textContent='Gemma is replying…';$('conversation').scrollTop=$('conversation').scrollHeight;}
      if(item.type==='done')complete=true;
    }
    if(!complete||!answer.trim())throw Error('No complete reply received. Check the Jetson connection.');
    history.push({role:'user',content:prompt},{role:'assistant',content:answer.slice(0,4000)});history=history.slice(-12);
    lastReply=answer;$('replay').hidden=false;$('question').value='';$('chat-status').textContent='Reply complete. Resume inspection when ready.';
    await say(answer);
  } catch(error) { $('chat-status').textContent=error.message;if(output&&!answer)output.textContent='No answer received.'; }
  finally {busy=false;$('send').disabled=false;}
};
async function poll(){await refresh();setTimeout(poll,state.demo?700:2000);}
async function pollConnections(){await connections();setTimeout(pollConnections,10000);}
poll();pollConnections();
