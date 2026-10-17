import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import MessageBubble from './MessageBubble.svelte';

// Baseline spec, "Language model": model output containing HTML or script is displayed as text.
describe('MessageBubble.svelte', () => {
	it('shows HTML and script in a reply as text, not markup', async () => {
		const content = '<img src=x onerror="alert(1)"><script>alert(2)</script><b>bold</b>';
		const { container } = render(MessageBubble, {
			message: { id: '1', role: 'assistant', content }
		});

		await expect.element(page.getByText(content)).toBeInTheDocument();
		expect(container.querySelector('img, script, b')).toBeNull();
	});

	it('links only https citations', async () => {
		const { container } = render(MessageBubble, {
			message: {
				id: '1',
				role: 'assistant',
				content: 'Answer',
				citations: [
					{ title: 'Migri', source_url: 'https://migri.fi', snippet: '' },
					{ title: 'Injected', source_url: 'javascript:alert(1)', snippet: '' }
				]
			}
		});

		await expect.element(page.getByText('Injected')).toBeInTheDocument();
		const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'));
		expect(hrefs).toEqual(['https://migri.fi/']);
	});
});
