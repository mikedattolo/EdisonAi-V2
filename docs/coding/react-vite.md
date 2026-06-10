# React + Vite Reference (Edison's frontend stack)

`apps/web` is a React 18 + TypeScript single-page app bundled by Vite. `src/App.tsx` holds the views as components; `src/api.ts` is the API client; `src/types.ts` shared types; `src/styles.css` the styles.

## Components & JSX
- A component is a function returning JSX: `function Panel({ title }: { title: string }) { return <section className="panel"><h3>{title}</h3></section>; }`.
- JSX rules: one root element (or `<>...</>` fragment); `className` not `class`; `htmlFor` not `for`; `{expr}` embeds JS; `style={{ color: 'red' }}` takes an object; self-close `<img />`.
- Lists need a stable `key`: `{items.map((it) => <li key={it.id}>{it.name}</li>)}`. Conditionals: `{cond && <X/>}` or `{cond ? <A/> : <B/>}`.
- Events: `onClick={() => fn()}`, `onChange={(e) => setX(e.target.value)}`, `onSubmit={(e) => { e.preventDefault(); ... }}`.

## Hooks (in this codebase)
- `const [v, setV] = useState<Type>(initial)` — local state; set with a value or updater `setV(prev => ...)`.
- `useEffect(() => { ...; return () => cleanup; }, [deps])` — run after render when deps change; `[]` = once on mount.
- `useRef<T>(null)` — mutable box / DOM ref (`<div ref={r}>`), doesn't trigger re-render.
- `useMemo(() => compute(a), [a])` cache a value; `useCallback(fn, [deps])` cache a function.
- Rules: call hooks at the top level of a component, never in loops/conditions. State updates are async + batched.

## Data flow & patterns
- Pass data down via props; lift shared state to the nearest common parent. Don't mutate state — create new objects/arrays (`[...arr]`, `{...obj}`).
- Fetch via the `edisonApi` client in `api.ts` (wraps `fetch`); call inside an effect or event handler, store results in state, render from state.
- Streaming (SSE): read `response.body.getReader()` and update state per chunk; this app does that for chat and the code agent.

## Vite build/run
- `npm run dev` — dev server with hot module reload (fast iteration).
- `npm run build` — `tsc` type-check then `vite build` → `apps/web/dist`.
- `npm run preview` — serve the built `dist` (this is what `edison-web` runs). The dev `vite.config.ts` proxies `/api` and `/health` to `127.0.0.1:8000`.
- Env vars: `import.meta.env.VITE_*` (must be prefixed `VITE_`).

## Editing Edison's UI specifically
- All views live in `App.tsx` — find a view component (e.g. `CreatorStudioView`, `MemoryView`, `CodeWorkspaceView`) and edit its JSX.
- Styles are class-based in `styles.css`; match an existing `className` to a rule. Add new shared types to `types.ts` and API calls to `api.ts`.
- After editing: `npm run build`, then restart `edison-web` (or use Apply & restart). A type error will fail `tsc` — fix it before the build passes.

## Good practices
- Keep components small and focused; derive values during render instead of storing redundant state.
- Always provide `key` in lists; clean up effects (timers, listeners, abort controllers).
- Guard async UI: disable buttons while a request is in flight; handle the error path.
