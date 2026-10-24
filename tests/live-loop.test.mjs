import {test} from 'node:test';
import assert from 'node:assert/strict';
import {LiveLoop} from '../circuit_lab/static/live-loop.mjs';
const wait = ms => new Promise(resolve=>setTimeout(resolve,ms));
test('keeps a single request in flight and ignores a paused generation',async()=>{
  let release, current, calls=0;
  const loop=new LiveLoop(async isCurrent=>{calls++;current=isCurrent;await new Promise(resolve=>{release=resolve;});},5);
  try {
    loop.start();
    await loop.tick();
    assert.equal(calls,1);
    assert.equal(current(),true);
    const old=current;
    loop.stop();loop.start();
    assert.equal(old(),false);
    assert.equal(calls,1,'resume must not overlap the old request');
    release();await wait(20);
    assert.equal(calls,2);
    assert.equal(current(),true);
    loop.stop();release();await wait(20);
    assert.equal(calls,2,'stop must not schedule another request');
  } finally {loop.stop();release?.();}
});
test('each completed request samples again, without a frame backlog',async()=>{
  let frame=1;const sampled=[];
  const loop=new LiveLoop(async()=>{sampled.push(frame);frame=9;if(sampled.length===2)loop.stop();},5);
  loop.start();await wait(30);loop.stop();assert.deepEqual(sampled,[1,9]);
});
