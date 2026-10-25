export async function* readEvents(stream) {
  const reader = stream.getReader(), decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline).trim(); buffer = buffer.slice(newline + 1);
        if (line) yield JSON.parse(line);
      }
      if (done) { if (buffer.trim()) yield JSON.parse(buffer); break; }
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
}
