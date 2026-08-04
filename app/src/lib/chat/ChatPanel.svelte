<script lang="ts">
	import { onMount } from 'svelte';
	import { ChatStore } from './chat-state.svelte';
	import MessageList from './MessageList.svelte';
	import ChatInput from './ChatInput.svelte';
	import AgentSidebar from './AgentSidebar.svelte';
	import { AUTO_ROUTE } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages.js';

	const chat = new ChatStore();

	onMount(() => {
		chat.loadAgents();
	});

	const currentAgentName = $derived(
		chat.selectedAgentId === AUTO_ROUTE
			? m.chat_auto_route()
			: (chat.agents.find((agent) => agent.id === chat.selectedAgentId)?.name ?? '')
	);
</script>

<div
	class="grid h-dvh grid-rows-[auto_1fr] bg-pine-950 text-pine-100 sm:grid-cols-[minmax(220px,20%)_1fr] sm:grid-rows-none"
>
	<AgentSidebar
		agents={chat.agents}
		selectedAgentId={chat.selectedAgentId}
		onchange={(id) => (chat.selectedAgentId = id)}
	/>

	<div class="flex min-w-0 flex-col">
		<header class="border-b border-pine-700 p-4">
			<h2 class="font-medium text-pine-100">{currentAgentName}</h2>
		</header>

		<MessageList messages={chat.messages} />

		{#if chat.error}
			<p class="px-4 pb-2 text-sm text-red-400">{chat.error}</p>
		{/if}

		<ChatInput disabled={chat.isStreaming} onsend={(text) => chat.sendMessage(text)} />
	</div>
</div>
