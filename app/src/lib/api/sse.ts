interface RawSSEEvent {
	event: string;
	data: string;
}

function parseEventBlock(raw: string): RawSSEEvent | null {
	let event = 'message';
	const dataLines: string[] = [];

	for (const line of raw.split('\n')) {
		if (line.startsWith('event:')) {
			event = line.slice('event:'.length).trim();
		} else if (line.startsWith('data:')) {
			dataLines.push(line.slice('data:'.length).trim());
		}
	}

	if (dataLines.length === 0) return null;
	return { event, data: dataLines.join('\n') };
}

/** Parse a `text/event-stream` response body into (event, data) pairs, tolerant of \r\n or \n. */
export async function* parseSSEStream(response: Response): AsyncGenerator<RawSSEEvent> {
	if (!response.body) return;

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');

			let boundary = buffer.indexOf('\n\n');
			while (boundary !== -1) {
				const parsed = parseEventBlock(buffer.slice(0, boundary));
				buffer = buffer.slice(boundary + 2);
				if (parsed) yield parsed;
				boundary = buffer.indexOf('\n\n');
			}
		}
	} finally {
		reader.releaseLock();
	}
}
