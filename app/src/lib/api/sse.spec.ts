import { describe, expect, it } from 'vitest';
import { parseSSEStream } from './sse';

function streamFromChunks(chunks: string[]): Response {
	const encoder = new TextEncoder();
	const stream = new ReadableStream<Uint8Array>({
		start(controller) {
			for (const chunk of chunks) {
				controller.enqueue(encoder.encode(chunk));
			}
			controller.close();
		}
	});
	return new Response(stream);
}

async function collect(response: Response) {
	const events = [];
	for await (const event of parseSSEStream(response)) {
		events.push(event);
	}
	return events;
}

describe('parseSSEStream', () => {
	it('parses events delimited by \\n\\n', async () => {
		const events = await collect(streamFromChunks(['event: token\ndata: hi\n\n']));
		expect(events).toEqual([{ event: 'token', data: 'hi' }]);
	});

	it('parses a CRLF blank-line terminator split across reads mid-pair', async () => {
		// The terminator is \r\n\r\n. Splitting right before the final \n means
		// neither chunk alone contains a matched \r\n pair for that last CRLF,
		// so per-chunk normalization (the old behavior) would miss the \n\n
		// boundary entirely. Normalizing the whole accumulated buffer instead
		// (the fix) still finds it once both reads have landed.
		const events = await collect(streamFromChunks(['event: token\r\ndata: hi\r\n\r', '\n']));
		expect(events).toEqual([{ event: 'token', data: 'hi' }]);
	});
});
