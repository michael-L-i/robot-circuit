// Keep one utterance and one synthesis request at a time; no audio backlog.
export class WorkbenchVoice {
  constructor(audio, status) {
    this.audio=audio;this.status=status;this.enabled=false;this.generation=0;
    this.lastText='';this.lastAt=0;this.url=null;this.controller=null;
  }
  stop(){this.generation++;this.controller?.abort();this.audio.pause();window.speechSynthesis?.cancel();}
  async say(text, force=false){
    if(!text||(!this.enabled&&!force))return;
    if(!force&&(this.audio.paused===false||window.speechSynthesis?.speaking))return;
    if(!force&&(text===this.lastText||Date.now()-this.lastAt<20000))return;
    this.stop();const version=this.generation;this.controller=new AbortController();
    this.lastText=text;this.lastAt=Date.now();this.status('Generating local voice…');
    try{
      const response=await fetch('/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.slice(0,1500)}),signal:this.controller.signal});
      if(!response.ok)throw Error('Local voice unavailable');
      const blob=await response.blob();if(version!==this.generation)return;
      if(this.url)URL.revokeObjectURL(this.url);
      this.url=URL.createObjectURL(blob);this.audio.src=this.url;
      try{await this.audio.play();this.status(`${response.headers.get('X-Speech-Engine')||'Local'} voice · playing on this Mac`);}
      catch{this.status('Voice ready. Press Play below to hear it.');}
    }catch(error){
      if(version!==this.generation)return;
      if(window.speechSynthesis){
        const utterance=new SpeechSynthesisUtterance(text);
        const local=window.speechSynthesis.getVoices().find(v=>v.localService&&v.lang.startsWith('en'));
        if(!local){this.status('Voice unavailable. Findings are shown below.');return;}
        utterance.voice=local;window.speechSynthesis.speak(utterance);this.status('Using the Mac browser voice');
      }else this.status('Voice unavailable. Findings are shown below.');
    }
  }
}
