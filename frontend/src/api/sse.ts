// Stream NDJSON-style SSE events from a fetch POST response.
// We use a manual reader because `EventSource` does not support POST.

export interface SseEvent {
  event: string;
  data: unknown;
}

export async function* readSse(response: Response): AsyncIterable<SseEvent> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const lines = frame.split('\n');
      let event = 'message';
      const dataLines: string[] = [];
      for (const l of lines) {
        if (l.startsWith('event:')) event = l.slice(6).trim();
        else if (l.startsWith('data:')) dataLines.push(l.slice(5).trim());
      }
      const raw = dataLines.join('\n');
      let data: unknown = raw;
      try {
        data = JSON.parse(raw);
      } catch {
        /* keep string */
      }
      yield { event, data };
    }
  }
}
