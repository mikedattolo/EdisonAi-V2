# JavaScript & TypeScript Reference

Edison's frontend is TypeScript (React + Vite). This covers modern JS/TS and the Node tooling.

## Running & tooling
- Node REPL: `node`; run a file: `node file.js` / `node --experimental-strip-types file.ts` (or compile first).
- npm scripts: `npm run dev|build|preview`; run a binary: `npx tsc --noEmit`, `npx vite build`.
- Type-check without emitting: `tsc --noEmit`. Deps: see `dependency-management.md` (npm/pnpm/yarn).

## Modern JavaScript (ES2020+)
- Declarations: `const` (default), `let` (reassignable); avoid `var`. Block-scoped.
- Types: string, number, boolean, null, undefined, bigint, symbol, object. Arrays `[]`, objects `{}`.
- Template literals: `` `${name} is ${age}` ``. Arrow fns: `const f = (a, b) => a + b;`.
- Destructuring: `const { x, y } = obj; const [a, b] = arr;`. Spread/rest: `{...obj}`, `[...arr]`, `f(...args)`.
- Optional chaining `obj?.a?.b`; nullish coalescing `x ?? fallback` (only null/undefined). Default params `f(a = 1)`.
- Modules: `import { a } from './m'; import D from './d'; export const x = 1; export default fn;`.
- Async: `async function f(){ const r = await fetch(url); const j = await r.json(); }`; `Promise.all([...])`; `try/catch` around await.
- Array methods: `map filter reduce find some every forEach flatMap sort includes`. `Object.entries/keys/values`, `JSON.parse/stringify`.

## TypeScript essentials
- Annotate: `const n: number = 1; function f(x: string): boolean {}`. Inference covers most locals.
- Interfaces/types: `interface User { id: string; name?: string; }`, `type ID = string | number;`, unions `'a' | 'b'`, generics `Array<T>`, `Record<string, number>`.
- Optional `?`, readonly, `as` casts (`value as Foo`), `satisfies`, `keyof`, `typeof`, utility types `Partial<T> Pick<T,K> Omit<T,K> Required<T>`.
- `strict` mode (on in this repo): handle `null | undefined`; narrow with `if (x)` / `typeof` / `in`.
- `tsconfig.json` controls compilation; `noEmit: true` here (Vite/esbuild does the transform; tsc just type-checks). Build = `tsc && vite build`.

## DOM & fetch (browser)
- `document.querySelector('.x')`, `el.addEventListener('click', fn)`, `el.classList.add/remove/toggle`.
- `fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data) })` → `await res.json()`. Check `res.ok`.
- Streaming (SSE-like) read: `const reader = res.body.getReader();` then loop `reader.read()` + `TextDecoder`.

## Idioms & gotchas
- `===` / `!==` (strict), never `==`. `[] == false` is true — avoid loose equality.
- `this` in arrow functions is lexical (preferred in callbacks). `const`-declare and avoid mutation where possible.
- Async errors: always `await` or `.catch()` promises; an unhandled rejection is silent. Wrap `await` in try/catch.
- Keep functions pure where possible; copy with spread instead of mutating shared state.
