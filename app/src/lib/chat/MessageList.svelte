<script lang="ts">
	import type { DisplayMessage } from './chat-state.svelte';
	import MessageBubble from './MessageBubble.svelte';

	interface Props {
		messages: DisplayMessage[];
	}

	let { messages }: Props = $props();
	let scrollAnchor: HTMLDivElement | undefined = $state();

	$effect(() => {
		const count = messages.length;
		const last = messages[count - 1];
		// Track the streaming message's own state, not just array length, so
		// autoscroll keeps pace as tokens are appended to the same bubble.
		void last?.content;
		void last?.isStreaming;
		if (count > 0) {
			scrollAnchor?.scrollIntoView({ behavior: 'smooth', block: 'end' });
		}
	});
</script>

<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
	{#each messages as message (message.id)}
		<MessageBubble {message} />
	{/each}
	<div bind:this={scrollAnchor}></div>
</div>
