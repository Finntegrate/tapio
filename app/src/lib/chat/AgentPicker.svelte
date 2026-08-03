<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';
	import { AUTO_ROUTE } from '$lib/api/types';
	import type { AgentSummary } from '$lib/api/types';

	interface Props {
		agents: AgentSummary[];
		selectedAgentId: string;
		onchange: (agentId: string) => void;
	}

	let { agents, selectedAgentId, onchange }: Props = $props();
</script>

<select
	value={selectedAgentId}
	onchange={(event) => onchange(event.currentTarget.value)}
	class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
>
	<option value={AUTO_ROUTE}>{m.chat_auto_route()}</option>
	{#each agents as agent (agent.id)}
		<option value={agent.id}>{agent.name} — {agent.title}</option>
	{/each}
</select>
