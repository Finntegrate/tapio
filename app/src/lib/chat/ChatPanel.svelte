<script lang="ts">
	import { onMount } from 'svelte';
	import { ChatStore } from './chat-state.svelte';
	import MessageList from './MessageList.svelte';
	import ChatInput from './ChatInput.svelte';
	import AgentPicker from './AgentPicker.svelte';

	const chat = new ChatStore();

	onMount(() => {
		chat.loadAgents();
	});
</script>

<div class="mx-auto flex h-dvh max-w-3xl flex-col">
	<header
		class="flex items-center justify-between border-b border-slate-200 p-4 dark:border-slate-800"
	>
		<h1 class="text-lg font-semibold">Tapio</h1>
		<AgentPicker
			agents={chat.agents}
			selectedAgentId={chat.selectedAgentId}
			onchange={(id) => (chat.selectedAgentId = id)}
		/>
	</header>

	<MessageList messages={chat.messages} />

	{#if chat.error}
		<p class="px-4 pb-2 text-sm text-red-600 dark:text-red-400">{chat.error}</p>
	{/if}

	<ChatInput disabled={chat.isStreaming} onsend={(text) => chat.sendMessage(text)} />
</div>
