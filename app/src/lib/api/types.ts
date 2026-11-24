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
	/** When the page was crawled, if the index records it. */
	crawl_date?: string | null;
	/** The fixed-format citation: "Title — URL", plus "(retrieved DATE)" when known. */
	formatted?: string;
}

export interface CitationEventData {
	citations: Citation[];
	/** True when retrieval found nothing citable, so the reply is the fixed no-source message. */
	no_source?: boolean;
}

export interface TokenEventData {
	text: string;
}

export interface ErrorEventData {
	message: string;
}

export interface HealthResponse {
	model_available: boolean;
	/** Availability per model role: `default`, each overridden guide, and `guardrail`. */
	models: Record<string, boolean>;
}

export type ChatStreamEvent =
	| { kind: 'routing'; data: RoutingEventData }
	| { kind: 'citation'; data: CitationEventData }
	| { kind: 'token'; data: TokenEventData }
	| { kind: 'done' }
	| { kind: 'error'; data: ErrorEventData };
