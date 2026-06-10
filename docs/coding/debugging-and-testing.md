# Debugging & Testing

How to find and fix problems, and verify changes, across the stacks Edison works with.

## A reliable debugging loop
1. Reproduce the failure and read the FULL error message + stack trace (top frame = where it threw; bottom of a Python traceback = the actual error).
2. Locate the file:line from the trace; read the surrounding code.
3. Form one hypothesis; add a log/print or inspect state to confirm it.
4. Make the smallest fix; re-run the exact repro; confirm it's gone and nothing else broke.
5. Don't repeat the same failing action — change the approach when a fix doesn't work.

## Python
- Print/inspect: `print(repr(x))`, `import logging; logging.warning("%s", x)`. Interactive: `breakpoint()` (drops into pdb: `n` next, `s` step, `c` continue, `p expr`, `q` quit).
- Syntax check fast: `python3 -m py_compile file.py`. Import check: `python -c "import module"`.
- Tracebacks read top→bottom; the last line is `ExceptionType: message`. Catch narrowly; print the exception in dev.
- Tests (pytest): `pytest -q`, one test `pytest path::name -x` (stop on first fail), `-k "expr"` filter, `-s` show prints. Assert with plain `assert`. On Edison: `.venv/bin/python -m pytest -q`.

## JavaScript / TypeScript (browser + node)
- `console.log/console.error/console.table`; browser DevTools: Console (errors), Network (requests/SSE — check status, response, whether the stream stays open), Sources (breakpoints), Elements (DOM/CSS).
- Type errors: run `tsc --noEmit` to surface them before runtime. A red squiggle / build failure usually pinpoints the file:line.
- React: a component not updating usually means state was mutated instead of replaced, or a missing dependency in `useEffect`. "Network error" on a long fetch/SSE often means the connection idled out — keep it alive or check the proxy.
- Tests: `npm test` (Vitest/Jest if configured). On Edison the gate is `npm run build` (tsc + vite) — a clean build means types and bundling are OK.

## Java
- Stack traces point to `Class.method(File.java:line)`. Common: `NullPointerException` (null deref — check the object before use), `ClassNotFoundException`/`NoClassDefFoundError` (classpath/dependency missing).
- `System.out.println` for quick checks; IDE/`jdb` for breakpoints. Tests: `mvn test` / `./gradlew test` (JUnit).

## Web / API issues
- Use `curl -s -w "%{http_code}"` to hit an endpoint directly and see the raw status/body, bypassing the UI. A 422 = request validation failed (the route exists); 404 = wrong path/route missing; 500 = server exception (check `journalctl --user -u edison-api`).
- For SSE/streaming: confirm bytes keep flowing; long idle gaps get dropped by proxies/browsers as a "network error".

## Verifying a change on Edison
- Backend: import-check (`PYTHONPATH=apps/api .venv/bin/python -c "import edison_core.main"`) then `pytest -q`, then restart `edison-api`.
- Frontend: `npm run build` (must pass `tsc`), then restart `edison-web`.
- Never restart a service whose code fails to import/build — fix first so the app stays up.
