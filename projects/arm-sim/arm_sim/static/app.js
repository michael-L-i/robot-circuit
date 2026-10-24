const $=id=>document.getElementById(id), canvas=$('scene'), ctx=canvas.getContext('2d');
let state=null,running=false,busy=false,mode='gemma',yaw=-.68,pitch=.65,zoom=1,drag=null;
let W=800,H=410;
function resize(){const box=canvas.getBoundingClientRect();W=box.width;H=box.height;const d=Math.min(devicePixelRatio,2);canvas.width=W*d;canvas.height=H*d;ctx.setTransform(d,0,0,d,0,0);draw();}
new ResizeObserver(resize).observe(canvas);
function project(p){const x=p[0]-.22,y=p[1],z=p[2]-.10;const a=x*Math.cos(yaw)-y*Math.sin(yaw),b=x*Math.sin(yaw)+y*Math.cos(yaw);const scale=Math.min(W/0.73,H/.68)*zoom;return [W*.49+a*scale,H*.63+(b*Math.sin(pitch)-z*Math.cos(pitch))*scale];}
function line(points,color,width=1){ctx.beginPath();points.map(project).forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap='round';ctx.lineJoin='round';ctx.stroke();}
function poly(points,color,stroke){ctx.beginPath();points.map(project).forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fillStyle=color;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke();}}
function rect(x,y,z,w,h,c){poly([[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]],c);}
function dot(p,r,color){const [x,y]=project(p);ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
function label(p,text,color='#a7bcae'){const [x,y]=project(p);ctx.font='10px ui-monospace, monospace';ctx.fillStyle=color;ctx.fillText(text,x,y);}
function box(x,y,z,w,h,d,color){rect(x,y,z,w,h,color);poly([[x,y+h,z],[x+w,y+h,z],[x+w,y+h,z-d],[x,y+h,z-d]],'#34463c');poly([[x+w,y,z],[x+w,y+h,z],[x+w,y+h,z-d],[x+w,y,z-d]],'#263b2e');}
function draw(){ctx.clearRect(0,0,W,H);ctx.fillStyle='#1b2823';ctx.fillRect(0,0,W,H);for(let x=-.15;x<.65;x+=.05)line([[x,-.3,0],[x,.3,0]],'#2a3b30');for(let y=-.3;y<.31;y+=.05)line([[-.15,y,0],[.65,y,0]],'#2a3b30');
// Breadboard, actual A-E / F-J strips drawn across each row.
box(.285,-.085,.052,.105,.20,.014,'#e0e1d0');rect(.334,-.08,.053,.008,.19,'#89958b');
for(let r=0;r<28;r++){for(let c=0;c<10;c++){const x=.294+c*.008+(c>=5?.008:0),y=-.071+r*.0064;dot([x,y,.054],1.1,'#657165');}if(r%5===0)label([.282,-.071+r*.0064,.055],String(r+1),'#aab9a8');}
line([[.289,-.08,.055],[.289,.105,.055]],'#cf7d6c');line([[.388,-.08,.055],[.388,.105,.055]],'#73a9c1');
// Mesh and test pad on insulated extension tabs, connected to the same input net.
rect(.336,.023,.065,.028,.024,'#cb8f60');for(let i=0;i<7;i++){line([[.336+i*.004,.023,.0652],[.336+i*.004,.047,.0652]],'#7c5436',.7);line([[.336,.023+i*.004,.0653],[.364,.023+i*.004,.0653]],'#efbc83',.7);}
rect(.338,-.047,.065,.024,.024,'#73bbc4');line([[.35,-.035,.065],[.375,-.035,.058],[.375,.035,.058],[.35,.035,.065]],'#5eaaaf',2);
label([.395,-.04,.065],'TEST PAD','#8adbe3');label([.395,.035,.065],'COPPER MESH','#e0b087');
// Resistor / LED / return, with explicit series connections.
line([[.35,.035,.065],[.315,.035,.065],[.315,-.01,.065]],'#c9c8b6',2);line([[.315,.016,.065],[.315,-.003,.065]],'#d2b580',8);line([[.315,.012,.065],[.315,.009,.065]],'#986c46',8);line([[.315,.003,.065],[.315,0,.065]],'#df8a4c',8);
line([[.315,-.01,.065],[.303,-.01,.067],[.303,-.04,.067],[.294,-.04,.055],[.294,-.08,.055],[.43,-.12,.03]],'#283c30',3);
const on=state?.electrical?.led_on;const lp=[.303,-.026,.076];if(on){const [x,y]=project(lp);const g=ctx.createRadialGradient(x,y,0,x,y,25);g.addColorStop(0,'#ff725999');g.addColorStop(1,'#ff725900');ctx.fillStyle=g;ctx.fillRect(x-25,y-25,50,50);}dot(lp,6,on?'#ff9570':'#80493f');
label([.275,-.03,.088],'LED',on?'#ffb393':'#97ab9a');
// Arduino-sized power source and dock.
box(.42,-.17,.03,.075,.06,.012,'#387d76');rect(.445,-.155,.032,.025,.03,'#213a32');label([.421,-.178,.04],'5V / GND');
box(.211,-.17,.065,.038,.04,.025,'#54665a');label([.19,-.18,.08],'PROBE DOCK');
if(state?.tool!=='probe')line([[.23,-.15,.07],[.23,-.15,.12]],'#72cdd1',5);
let jumper=state?.jumper_xyz||[.31,.08,.065];if(state?.tool==='jumper')jumper=state.tcp;
line([[.44,-.13,.033],[.42,-.05,.15],[jumper[0]+.04,jumper[1],.14],jumper],'#e76b5f',3);line([jumper,[jumper[0],jumper[1],jumper[2]+.018]],'#dbcaa4',3);
// Simplified YAM links, with points from official-URDF FK.
box(-.045,-.045,.025,.09,.09,.025,'#506658');
if(state){const p=state.links;for(let i=1;i<p.length;i++){line([p[i-1],p[i]],'#0c1611',i<5?21:12);line([p[i-1],p[i]],i===3?'#9eb5a1':'#5e7a67',i<5?15:8);dot(p[i],i<5?7:4,'#a5b5a4');}const t=state.tcp;line([[t[0]-.012,t[1],t[2]+.025],[t[0]-.012,t[1],t[2]],[t[0]-.005,t[1],t[2]]],'#d2d7cb',3);line([[t[0]+.012,t[1],t[2]+.025],[t[0]+.012,t[1],t[2]],[t[0]+.005,t[1],t[2]]],'#d2d7cb',3);if(state.tool==='probe'){line([[t[0],t[1],t[2]+.04],t],'#7ed6de',5);line([t,[t[0],t[1],0]],'#6fa89844',1);}}
label([-.04,.055,.02],'YAM ULTRA / v1');}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointerup=()=>drag=null;canvas.onpointermove=e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.008;pitch=Math.max(.15,Math.min(1.4,pitch+(e.clientY-drag[1])*.007));drag=[e.clientX,e.clientY];draw();};canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(.65,Math.min(1.8,zoom-e.deltaY*.001));draw();};
const physics=$('physics'), videos=[$('motion0'),$('motion1')];
let visibleVideo=-1, urls=[null,null];
const isPhysics=()=>state?.backend==='mujoco';
function clearPlayback(){for(let i=0;i<2;i++){videos[i].pause();videos[i].hidden=true;videos[i].removeAttribute('src');videos[i].load();if(urls[i])URL.revokeObjectURL(urls[i]);urls[i]=null;}visibleVideo=-1;}
function view(){physics.hidden=!isPhysics()||visibleVideo>=0;canvas.hidden=isPhysics();$('legend').hidden=isPhysics();}
function still(){if(isPhysics()&&!running&&visibleVideo<0)physics.src=`api/render.jpg?camera=${$('camera').value}&r=${state.revision}-${Date.now()}`;}
async function api(path,data){const r=await fetch('api/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const b=await r.json();if(!r.ok)throw Error(b.detail||'Request failed');return b;}
function controls(){for(const id of ['run','step','baseline','reset','unload','scenario','offset','probeoffset','backend','perception','camera','seed'])$(id).disabled=busy||running;$('pause').disabled=!running;for(const id of ['run','step','baseline'])$(id).disabled=busy||running||!!state?.done;}
function render(){view();if(!isPhysics())draw();still();const last=state.measurements.at(-1);$('voltage').replaceChildren(document.createTextNode(last?.voltage==null?'—':last.voltage.toFixed(2)));const small=document.createElement('small');small.textContent=' V';$('voltage').append(small);$('contact').textContent=last?(last.valid_contact?'Last measured sample · reference: GND':'No pad contact · reading unavailable'):'No sample yet · reference: GND';$('led').textContent=state.electrical.led_on?'● ON':'● OFF';$('led').style.color=state.electrical.led_on?'#ffad86':'#829b89';$('current').textContent=state.electrical.current_ma.toFixed(2)+' mA';$('tool').textContent=state.tool||'Empty';$('counter').textContent=String(state.revision).padStart(2,'0')+' ACTIONS';$('phase').textContent=state.done?(state.success?'Repair verified':'Stopped — inspect trace'):(state.events.at(-1)?.note||'Ready at home');
$('perception-status').textContent=state.perception?`LAST CAMERA DETECTIONS: ${Object.keys(state.perception.detections).join(', ')||'none'}`:'ORACLE BASELINE · simulator supplies target coordinates';
const trace=$('trace');trace.replaceChildren();for(const ev of state.events){const row=document.createElement('div');row.className='event';const n=document.createElement('span');n.textContent=String(ev.step).padStart(2,'0');const body=document.createElement('div');body.textContent=ev.note;const detail=document.createElement('p');detail.textContent=ev.decision?`${ev.decision.source} · ${ev.decision.seconds}s · ${ev.decision.reason}`:'';body.append(detail);row.append(n,body);trace.append(row);}trace.scrollTop=trace.scrollHeight;}
function progressWatch(){let pending=false;let stopped=false;async function poll(){if(pending||stopped)return;pending=true;try{const p=await api('progress');if(stopped)return;const labels={perception:'Locating markers in camera image',inference:'Gemma is selecting the next skill',physics:'Executing MuJoCo physics',rendering:'Rendering 720p motion',ready:'Preparing motion playback',playback:'Preparing motion playback'};if(labels[p.phase])$('status').textContent=`${labels[p.phase]} · ${p.elapsed}s${p.model_seconds!=null?' · model '+p.model_seconds+'s':''}`;}catch{}finally{pending=false;}}const timer=setInterval(poll,750);return ()=>{stopped=true;clearInterval(timer);};}
async function animate(result,onReady=()=>{}){if(!isPhysics())return animate2d(result);
const index=visibleVideo===0?1:0, next=videos[index];
const response=await fetch(`api/action.mp4?camera=${$('camera').value}&r=${result.state.revision}&episode=${encodeURIComponent(result.state.episode)}`);
if(!response.ok){const error=await response.json();throw Error(error.detail||'Video generation failed');}
if(urls[index])URL.revokeObjectURL(urls[index]);urls[index]=URL.createObjectURL(await response.blob());
await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Video decode timed out')),30000);next.onloadeddata=()=>{clearTimeout(timeout);resolve();};next.onerror=()=>{clearTimeout(timeout);reject(Error('Unable to decode motion video'));};next.src=urls[index];next.load();});
if(visibleVideo>=0)videos[visibleVideo].hidden=true;physics.hidden=true;next.hidden=false;visibleVideo=index;
onReady();$('status').textContent=`Playing ${result.decision.action} · Gemma ${result.decision.seconds}s`;
await new Promise((resolve,reject)=>{next.onended=resolve;next.onerror=()=>reject(Error('Motion playback failed'));next.play().catch(reject);});
// Leave the ended video on its final frame during the next inference/encoding stage.
state=result.state;render();}
function animate2d(result){return new Promise(resolve=>{let i=0,elapsed=0,previous=0;state=result.before;function frame(now){if(!previous)previous=now;elapsed+=(now-previous)/1000;previous=now;while(i<result.frames.length&&elapsed>=result.frames[i].dt){elapsed-=result.frames[i].dt;Object.assign(state,result.frames[i++]);}draw();if(i<result.frames.length)requestAnimationFrame(frame);else{state=result.state;render();resolve();}}requestAnimationFrame(frame);});}
async function step(){if(busy)return;busy=true;controls();let stopProgress=progressWatch();$('status').textContent='Acquiring camera observations…';try{const result=await api('step',{mode,revision:state.revision,episode:state.episode});$('reason').textContent=result.decision.reason;await animate(result,stopProgress);if(state.done){running=false;$('status').textContent=state.success?'Verified: measured voltage and LED agree.':'Stopped without claiming a repair.';}}catch(e){running=false;$('status').textContent=e.message+' Refresh state before retrying.';}finally{stopProgress();busy=false;controls();}}
async function run(selected){mode=selected;running=true;controls();while(running&&!state.done){await step();if(document.hidden){running=false;$('status').textContent='Paused because this tab is hidden.';}}running=false;controls();}
$('run').onclick=()=>run('gemma');$('baseline').onclick=()=>run('scripted');$('step').onclick=()=>{mode='gemma';step();};$('pause').onclick=()=>{running=false;$('status').textContent='Pausing after the current action.';controls();};
$('reset').onclick=async()=>{busy=true;controls();try{state=await api('reset',{seed:Number($('seed').value),backend:$('backend').value,perception:$('perception').value,scenario:$('scenario').value,placement_error_mm:Number($('offset').value),probe_error_mm:Number($('probeoffset').value)});clearPlayback();$('reason').textContent='Ready for a new run.';$('status').textContent='Reset complete. Camera targets will be measured before motion.';render();}catch(e){$('status').textContent=e.message;}finally{busy=false;controls();}};
$('unload').onclick=async()=>{try{await api('unload',{});$('status').textContent='Model unloaded; next AI action will load it again.';}catch(e){$('status').textContent=e.message;}};
$('camera').onchange=()=>{if(!busy){clearPlayback();view();still();}};
state=await api('state');$('seed').value=state.config.seed;$('backend').value=state.backend||'kinematic';$('perception').value=state.perception_mode||'oracle';$('scenario').value=state.config.scenario;$('offset').value=state.config.placement_error_mm;$('probeoffset').value=state.config.probe_error_mm;render();if(state.events.at(-1)?.decision)$('reason').textContent=state.events.at(-1).decision.reason;if(state.done)$('status').textContent=state.success?'Verified: measured voltage and LED agree. Reset to run again.':'Stopped without claiming a repair. Reset to run again.';controls();
