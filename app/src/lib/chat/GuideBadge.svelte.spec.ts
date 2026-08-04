import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import GuideBadge from './GuideBadge.svelte';

describe('GuideBadge.svelte', () => {
	it('renders the guide name and title', async () => {
		render(GuideBadge, { name: 'Ilmarinen', title: 'Craftsman of documentation', color: 'forest' });

		await expect.element(page.getByText('Ilmarinen')).toBeInTheDocument();
		await expect
			.element(page.getByText('Craftsman of documentation', { exact: false }))
			.toBeInTheDocument();
	});

	it('renders without a title', async () => {
		render(GuideBadge, { name: 'Tapio' });

		await expect.element(page.getByText('Tapio')).toBeInTheDocument();
	});
});
