# Python Reference (3.11+)

Edison's backend is Python (FastAPI + pydantic) on Python 3.12 in a venv. This covers the language and the tools you'll use here.

## Running & tooling
- Run a file: `python3 file.py`; module: `python3 -m pytest`; REPL: `python3`; check syntax fast: `python3 -m py_compile file.py`.
- Format/lint (if installed): `ruff check .`, `ruff format .`, `black .`, `mypy .`. Tests: `pytest -q`, `pytest path::test_name -x`.
- Deps: see `dependency-management.md` (pip + venv). On Edison use `.venv/bin/python` / `.venv/bin/pip`.

## Core syntax
- Variables are dynamically typed; blocks use indentation (4 spaces), not braces.
- Types: `int float str bool bytes None`; containers `list [] tuple () dict {} set {}`.
- f-strings: `f"{name}={value:.2f}"`. Multiline: triple quotes `"""..."""`.
- Control: `if/elif/else`, `for x in iterable:`, `while`, `break/continue`, `match/case` (3.10+).
- Comprehensions: `[x*2 for x in xs if x>0]`, `{k: v for k, v in items}`, generator `(x for x in xs)`.
- Functions: `def f(a, b=1, *args, **kwargs) -> int:`; lambdas `lambda x: x+1`; keyword-only after `*`.
- Unpacking: `a, *rest = seq`; `**dict1, **dict2` merge; `dict | dict2` (3.9+).

## Type hints (used heavily in this codebase)
- `from __future__ import annotations` (lazy eval) is at the top of most files here.
- `def f(x: int, items: list[str], opt: str | None = None) -> dict[str, Any]:`
- `Literal["a","b"]`, `Optional[T]` == `T | None`, `Callable[[int], str]`, `TYPE_CHECKING` for import-only-for-types.

## Errors & resources
- `try: ... except ValueError as e: ... except (TypeError, KeyError): ... else: ... finally: ...`
- Raise: `raise ValueError("msg")`; chain `raise X from err`. Custom: `class MyError(Exception): pass`.
- Context managers: `with open(path) as f: ...`; `pathlib.Path(p).read_text(encoding="utf-8")`.

## Stdlib you'll reach for
- `pathlib.Path` (paths), `json` (loads/dumps), `re` (regex), `dataclasses.dataclass`, `enum.Enum`, `typing`, `datetime`, `subprocess.run([...], capture_output=True, text=True, timeout=...)`, `os`, `sys`, `itertools`, `collections` (defaultdict, Counter), `uuid`, `hashlib`, `logging`.

## FastAPI + pydantic (this app's stack)
- Pydantic v2 models: `class Req(BaseModel): name: str = Field(min_length=1); items: list[str] = Field(default_factory=list)`. Serialize: `model.model_dump(mode="json")`; parse: `Model(**data)`.
- Routes: `router = APIRouter(prefix="/api/v1/x")`; `@router.post("/y", response_model=Resp)` `def handler(payload: Req, dep = Depends(get_dep)) -> Resp: ...`. Errors: `raise HTTPException(status_code=400, detail="...")`.
- Streaming: `return StreamingResponse(gen(), media_type="text/event-stream")` for SSE.
- Async: `async def` for awaitable I/O; keep blocking calls (sync httpx, subprocess) off the event loop or in a thread.

## Idioms & gotchas
- Default args are evaluated once — never use a mutable default (`def f(x=[])`); use `None` + create inside.
- Truthiness: empty containers/`0`/`""`/`None` are falsy. Prefer `if not items:`.
- Iterate dicts: `for k, v in d.items()`. Use `.get(k, default)` to avoid KeyError.
- Prefer f-strings over `%`/`.format`. Prefer comprehensions over manual loops for transforms.
