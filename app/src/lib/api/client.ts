import { env } from '$env/dynamic/public';
import * as m from '$lib/paraglide/messages.js';
import { parseSSEStream } from './sse';
import type {
	AgentSummary,
	ChatMessage,
	ChatStreamEvent,
	CitationEventData,
	ErrorEventData,
	HealthResponse,
	RoutingEventData,
	TokenEventData
} from './types';

const API_BASE_URL = env.PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function getHealth(): Promise<HealthResponse> {
	const response = await fetch(`${API_BASE_URL}/health`);
	if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
	return response.json();
}

export async function getAgents(): Promise<AgentSummary[]> {
	const response = await fetch(`${API_BASE_URL}/agents`);
	if (!response.ok) throw new Error(`Failed to load guides: ${response.status}`);
	return response.json();
}

interface ChatStreamRequest {
	message: string;
	history: ChatMessage[];
	agent_id: string;
}

/** Stream one chat turn's SSE events: routing, citation, token(s), then done or error. */
export async function* streamChat(
	body: ChatStreamRequest,
	options: { signal?: AbortSignal } = {}
): AsyncGenerator<ChatStreamEvent> {
	const response = await fetch(`${API_BASE_URL}/chat/stream`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
		signal: options.signal
	});

	if (!response.ok || !response.body) {
		yield { kind: 'error', data: { message: m.chat_send_error() } };
		return;
	}

	for await (const { event, data } of parseSSEStream(response)) {
		switch (event) {
			case 'routing':
				yield { kind: 'routing', data: JSON.parse(data) as RoutingEventData };
				break;
			case 'citation':
				yield { kind: 'citation', data: JSON.parse(data) as CitationEventData };
				break;
			case 'token':
				yield { kind: 'token', data: JSON.parse(data) as TokenEventData };
				break;
			case 'error':
				yield { kind: 'error', data: JSON.parse(data) as ErrorEventData };
				break;
			case 'done':
				yield { kind: 'done' };
				break;
		}
	}
}
