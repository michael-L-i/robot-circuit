import {LiveLoop} from './live-loop.mjs';
const $=id=>document.getElementById(id);
const token=location.hash.slice(1)||sessionStorage.getItem('circuit-pair');
if(token)sessionStorage.setItem('circuit-pair',token);
history.replaceState(null,'',location.pathname);
let stream=null,wake=null,generation=0,count=0;
const canvas=document.createElement('canvas');
const loop=new LiveLoop(async()=>{
 if(!stream||!$('video').videoWidth)return;
 try{
  const v=$('video'),ratio=Math.min(1,1280/Math.max(v.videoWidth,v.videoHeight));
  canvas.width=Math.round(v.videoWidth*ratio);canvas.height=Math.round(v.videoHeight*ratio);
  canvas.getContext('2d').drawImage(v,0,0,canvas.width,canvas.height);
  const r=await fetch('/api/phone/frame',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({image:canvas.toDataURL('image/jpeg',.9)}),signal:AbortSignal.timeout(20000)});
  if(!r.ok){const d=await r.json();throw Error(d.detail||'Upload failed');}
  count++;$('status').textContent=`Connected · ${count} frames sent. Last: ${new Date().toLocaleTimeString()}. Next in 2 seconds.`;
 }catch(e){$('status').textContent=`${e.message}. Retrying in 2 seconds…`;}
},2000);
function stop(){generation++;loop.stop();stream?.getTracks().forEach(t=>t.stop());stream=null;$('video').srcObject=null;$('stop').disabled=true;$('live').disabled=!isSecureContext||!token;wake?.release();wake=null;}
async function keepAwake(){try{if(stream)wake=await navigator.wakeLock?.request('screen');}catch{}}
$('live').onclick=async()=>{
 stop();const version=generation;$('live').disabled=true;$('stop').disabled=false;
 try{
  const incoming=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});
  if(version!==generation){incoming.getTracks().forEach(t=>t.stop());return;}
  stream=incoming;$('video').srcObject=stream;await $('video').play();await keepAwake();
  $('status').textContent='Camera running. Sending the first frame…';loop.start();
 }catch(e){stop();$('status').textContent=`Camera unavailable: ${e.message}. Allow camera access in Safari.`;}
};
$('stop').onclick=()=>{stop();$('status').textContent='Camera stopped.';};
window.addEventListener('pagehide',stop);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')keepAwake();});
$('live').disabled=!isSecureContext||!token;
if(!token)$('status').textContent='Scan the QR on your Mac to pair this camera.';
else if(!isSecureContext)$('status').textContent='Open the HTTPS camera link from your Mac QR code. Safari needs HTTPS to stream.';
