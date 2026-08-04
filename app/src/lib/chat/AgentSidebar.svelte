<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';
	import { AUTO_ROUTE } from '$lib/api/types';
	import type { AgentSummary } from '$lib/api/types';
	import { AGENT_DOT_CLASSES } from './agent-colors';

	interface Props {
		agents: AgentSummary[];
		selectedAgentId: string;
		onchange: (agentId: string) => void;
	}

	let { agents, selectedAgentId, onchange }: Props = $props();
</script>

<aside
	class="flex max-h-48 min-h-0 flex-col overflow-hidden border-b border-pine-700 bg-pine-900 sm:h-full sm:max-h-none sm:border-r sm:border-b-0"
>
	<div class="shrink-0 border-b border-pine-700 p-4">
		<h1 class="text-lg font-semibold text-pine-100">Tapio</h1>
		<p class="text-xs text-pine-400">{m.chat_sidebar_tagline()}</p>
	</div>

	<nav class="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
		<button
			type="button"
			onclick={() => onchange(AUTO_ROUTE)}
			class="w-full rounded-lg p-3 text-left transition-colors hover:bg-pine-800 {selectedAgentId ===
			AUTO_ROUTE
				? 'bg-pine-800 ring-1 ring-lichen-500/50'
				: ''}"
		>
			<span class="font-medium text-pine-100">{m.chat_auto_route()}</span>
		</button>

		{#each agents as agent (agent.id)}
			<button
				type="button"
				onclick={() => onchange(agent.id)}
				class="w-full rounded-lg p-3 text-left transition-colors hover:bg-pine-800 {selectedAgentId ===
				agent.id
					? 'bg-pine-800 ring-1 ring-lichen-500/50'
					: ''}"
			>
				<span class="flex items-center gap-2">
					<span
						class="h-2 w-2 shrink-0 rounded-full {AGENT_DOT_CLASSES[agent.color] ?? 'bg-pine-400'}"
					></span>
					<span class="font-medium text-pine-100">{agent.name}</span>
				</span>
				<p class="mt-0.5 text-xs text-pine-400">{agent.title}</p>
				<p class="mt-1 line-clamp-2 text-xs text-pine-300">{agent.summary}</p>
			</button>
		{/each}
	</nav>
</aside>
