<script module>
	import { defineMeta } from '@storybook/addon-svelte-csf';
	import GuideBadge from './GuideBadge.svelte';

	const { Story } = defineMeta({
		title: 'Chat/GuideBadge',
		component: GuideBadge,
		tags: ['autodocs']
	});
</script>

<Story
	name="Forest"
	args={{ name: 'Ilmarinen', title: 'Craftsman of documentation', color: 'forest' }}
/>
<Story name="Amber" args={{ name: 'Sampo', title: 'Prosperity guide', color: 'amber' }} />
<Story name="Nordic" args={{ name: 'Rauni', title: 'Prosperity guardian', color: 'nordic' }} />
<Story name="NoTitle" args={{ name: 'Tapio' }} />
