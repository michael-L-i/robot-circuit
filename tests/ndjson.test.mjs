import test from 'node:test';
import assert from 'node:assert/strict';
import {readEvents} from '../circuit_lab/static/ndjson.mjs';

test('stream parser handles split UTF-8, split lines, and final line without newline', async()=>{
  const bytes=new TextEncoder().encode('{"type":"text","text":"café →"}\n{"type":"done"}');
  const stream=new ReadableStream({start(controller){for(const byte of bytes)controller.enqueue(new Uint8Array([byte]));controller.close();}});
  const events=[];for await(const event of readEvents(stream))events.push(event);
  assert.deepEqual(events,[{type:'text',text:'café →'},{type:'done'}]);
});
test('invalid response is not silently treated as completion',async()=>{
  const stream=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('not json\n'));c.close();}});
  await assert.rejects(async()=>{for await(const event of readEvents(stream))void event;});
});
