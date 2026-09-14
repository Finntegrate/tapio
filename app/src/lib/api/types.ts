export const AUTO_ROUTE = 'auto';

export interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
}

export interface AgentSummary {
	id: string;
	name: string;
	title: string;
	category: string;
	summary: string;
	color: string;
}

export interface RoutingEventData {
	agent_id: string;
	name: string;
	title: string;
	category: string;
	reason: string;
	was_explicit: boolean;
}

export interface Citation {
	title: string;
	source_url: string;
	snippet: string;
}

export interface CitationEventData {
	citations: Citation[];
}

export interface TokenEventData {
	text: string;
}

export interface ErrorEventData {
	message: string;
}

export interface HealthResponse {
	model_available: boolean;
}

export type ChatStreamEvent =
	| { kind: 'routing'; data: RoutingEventData }
	| { kind: 'citation'; data: CitationEventData }
	| { kind: 'token'; data: TokenEventData }
	| { kind: 'done' }
	| { kind: 'error'; data: ErrorEventData };
