# sv

Everything you need to build a Svelte project, powered by [`sv`](https://github.com/sveltejs/cli).

## Creating a project

If you're seeing this, you've probably already done this step. Congrats!

```sh
# create a new project
npx sv create my-app
```

To recreate this project with the same configuration:

```sh
# recreate this project
npx sv@0.17.0 create --template minimal --types ts --add prettier eslint vitest="usages:unit,component" playwright tailwindcss="plugins:typography,forms" sveltekit-adapter="adapter:auto" paraglide="languageTags:en, fi+demo:no" storybook ai-tools="ide:claude-code,vscode,gemini+delivery:plugin+tools:mcp,svelte-code-writer,svelte-core-bestpractices,svelte-file-editor+mcpSetup:remote" --install npm app
```

## Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
npm run dev

# or start the server and open the app in a new browser tab
npm run dev -- --open
```

## Testing

`npm run check` type checks the app with svelte-check (it compiles the Paraglide messages first, so it works on a fresh checkout).

`npm run test:unit` runs Vitest, which `vite.config.ts` splits into three projects:

| Project     | Files                                 | Runs in                                                                                |
| ----------- | ------------------------------------- | -------------------------------------------------------------------------------------- |
| `server`    | `src/**/*.{test,spec}.{js,ts}`        | Node, for plain TypeScript such as the SSE parser                                      |
| `client`    | `src/**/*.svelte.{test,spec}.{js,ts}` | Headless Chromium via Playwright, for components rendered with `vitest-browser-svelte` |
| `storybook` | `*.stories.svelte`                    | Headless Chromium, one test per story                                                  |

Every test must make at least one assertion (`expect.requireAssertions`). The browser projects need Chromium once: `npx playwright install chromium`.

CI runs the server and client projects:

```sh
npm run test:unit -- --run --project server --project client
```

The storybook project is not in CI yet: its addon setup fails to load (an `aria-query` export error, and on Node 22 a module-loading race in the Chromatic addon).

## Building

To create a production version of your app:

```sh
npm run build
```

You can preview the production build with `npm run preview`.

> To deploy your app, you may need to install an [adapter](https://svelte.dev/docs/kit/adapters) for your target environment.
