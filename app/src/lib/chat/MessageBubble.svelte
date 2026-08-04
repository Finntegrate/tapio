<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';
	import type { DisplayMessage } from './chat-state.svelte';
	import GuideBadge from './GuideBadge.svelte';
	import CitationList from './CitationList.svelte';

	interface Props {
		message: DisplayMessage;
	}

	let { message }: Props = $props();
</script>

<div class="flex flex-col gap-1 {message.role === 'user' ? 'items-end' : 'items-start'}">
	{#if message.role === 'assistant' && message.routing}
		<div class="flex flex-col gap-0.5">
			<GuideBadge name={message.routing.name} title={message.routing.title} color={message.color} />
			<span class="text-xs text-pine-400">{message.routing.reason}</span>
		</div>
	{/if}

	<div
		class="max-w-2xl rounded-2xl px-4 py-2 {message.role === 'user'
			? 'bg-emerald-700 text-white'
			: 'bg-pine-800 text-pine-100'}"
	>
		{#if message.content}
			<p class="whitespace-pre-wrap">{message.content}</p>
		{:else if message.isStreaming}
			<p class="text-pine-400 italic">{m.chat_thinking()}</p>
		{/if}
	</div>

	{#if message.citations && message.citations.length > 0}
		<CitationList citations={message.citations} />
	{/if}
</div>
