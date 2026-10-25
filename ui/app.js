const $ = id => document.getElementById(id);
const audio=$('voice');
let busy=false, audioURL=null;
function status(text){$('status').textContent=text;}
async function json(url, options){
  const response=await fetch(url,options);
  const body=await response.json();
  if(!response.ok)throw Error(body.detail||'Request failed');
  return body;
}
function stopVoice(){audio.pause();audio.currentTime=0;document.body.classList.remove('speaking');$('stop').hidden=true;}
audio.addEventListener('playing',()=>{document.body.classList.add('speaking');$('stop').hidden=false;status('Speaking through this Mac.');});
function quiet(){document.body.classList.remove('speaking');$('stop').hidden=true;}
audio.addEventListener('pause',quiet);
audio.addEventListener('ended',()=>{quiet();status('Analysis complete. Click Analyze board for another frame.');});
audio.addEventListener('error',()=>{quiet();status('Audio playback failed. The analysis is shown above.');});
async function play(){try{await audio.play();}catch{status('Voice is ready. Click Play voice to hear it.');}}
$('replay').onclick=()=>{audio.currentTime=0;play();};
$('stop').onclick=()=>{stopVoice();status('Voice stopped.');};
$('analyze').onclick=async()=>{
  if(busy)return;
  busy=true;$('analyze').disabled=true;stopVoice();$('replay').hidden=true;
  if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null;audio.removeAttribute('src');}
  $('capture').hidden=true;$('transcript').textContent='';
  document.body.dataset.state='thinking';status('Taking the latest phone-camera frame and asking Gemma on the Jetson…');
  try{
    const result=await json('/api/analyze-board',{method:'POST',signal:AbortSignal.timeout(210000)});
    const line=document.createElement('p');line.className='line now';line.textContent=result.text;$('transcript').append(line);
    $('frame').src=result.image;$('capture').hidden=false;
    $('frame-label').textContent=`Frame ${result.frame_sequence} · ${new Date(result.received_at*1000).toLocaleTimeString()} · ${result.model}`;
    document.body.dataset.state='active';status('Analysis ready. Preparing the Mac voice…');
    const response=await fetch('/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:result.text.slice(0,1500)}),signal:AbortSignal.timeout(105000)});
    if(!response.ok)throw Error('Voice unavailable. The real Gemma analysis is shown above.');
    audioURL=URL.createObjectURL(await response.blob());audio.src=audioURL;$('replay').hidden=false;
    await play();
  }catch(error){document.body.dataset.state='idle';status(error.message||'Could not analyze the board.');}
  finally{busy=false;$('analyze').disabled=false;}
};
async function connectionStatus(){
  try{
    const info=await json('/api/status');
    const fresh=info.received_at && Date.now()/1000-info.received_at<=30;
    status(!info.inference.reachable?'Jetson disconnected. Restore its SSH tunnel before analyzing.':!fresh?'Jetson ready. Open the paired phone camera before analyzing.':`${info.inference.model} on Jetson · camera ready. Click Analyze board.`);
  }catch(error){status(error.message);}
}
connectionStatus();
