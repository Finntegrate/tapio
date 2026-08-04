import * as m from '$lib/paraglide/messages.js';
import { getAgents, streamChat } from '$lib/api/client';
import { AUTO_ROUTE } from '$lib/api/types';
import type { AgentSummary, ChatMessage, Citation, RoutingEventData } from '$lib/api/types';

export interface DisplayMessage {
	id: string;
	role: 'user' | 'assistant';
	content: string;
	routing?: RoutingEventData;
	color?: string;
	citations?: Citation[];
	isStreaming?: boolean;
}

export class ChatStore {
	messages = $state<DisplayMessage[]>([]);
	agents = $state<AgentSummary[]>([]);
	selectedAgentId = $state<string>(AUTO_ROUTE);
	isStreaming = $state(false);
	error = $state<string | null>(null);

	async loadAgents(): Promise<void> {
		try {
			this.agents = await getAgents();
		} catch {
			this.error = m.chat_agents_error();
		}
	}

	async sendMessage(text: string): Promise<void> {
		const trimmed = text.trim();
		if (!trimmed || this.isStreaming) return;

		const history: ChatMessage[] = this.messages.map((message) => ({
			role: message.role,
			content: message.content
		}));

		this.messages.push(
			{ id: crypto.randomUUID(), role: 'user', content: trimmed },
			{ id: crypto.randomUUID(), role: 'assistant', content: '', isStreaming: true }
		);
		// Re-read the pushed message back out of the $state array so mutations below
		// go through Svelte's reactive proxy, not the original plain object reference.
		const assistantMessage = this.messages[this.messages.length - 1];

		this.isStreaming = true;
		this.error = null;

		try {
			for await (const event of streamChat({
				message: trimmed,
				history,
				agent_id: this.selectedAgentId
			})) {
				switch (event.kind) {
					case 'routing':
						assistantMessage.routing = event.data;
						assistantMessage.color = this.agents.find(
							(agent) => agent.id === event.data.agent_id
						)?.color;
						break;
					case 'citation':
						assistantMessage.citations = event.data.citations;
						break;
					case 'token':
						assistantMessage.content += event.data.text;
						break;
					case 'error':
						this.error = event.data.message;
						break;
					case 'done':
						break;
				}
			}
		} catch {
			this.error = m.chat_send_error();
		} finally {
			assistantMessage.isStreaming = false;
			this.isStreaming = false;
		}
	}
}
