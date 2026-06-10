# Dependency Management Cheat Sheet (per language)

How to add, install, pin, and audit dependencies in each ecosystem. On the Edison box, prefer the project's existing tool (pip+venv for the API, npm for the web app).

## Python — pip + venv (what Edison's API uses)
- Create venv: `python3 -m venv .venv` then activate `source .venv/bin/activate` (or call `.venv/bin/python` / `.venv/bin/pip` directly, no activation needed).
- Install: `pip install requests` ; specific version `pip install "requests==2.32.3"` ; range `pip install "fastapi>=0.115,<1.0"`.
- From a file: `pip install -r requirements.txt`. Freeze: `pip freeze > requirements.txt`.
- Project metadata: declare runtime deps in `pyproject.toml` under `[project] dependencies = [...]`; install the project editable with `pip install -e .` (and `pip install -e ".[dev]"` for the `dev` extras).
- Upgrade: `pip install -U <pkg>`. Uninstall: `pip uninstall <pkg>`. Show: `pip show <pkg>`. List: `pip list`.
- Faster alternatives (same registry): `uv pip install <pkg>` / `uv venv`. Poetry: `poetry add <pkg>`, `poetry install`. Conda: `conda install <pkg>`.

## Node / JavaScript / TypeScript — npm (what Edison's web app uses)
- Install all from `package.json`: `npm install` (or reproducible `npm ci`, needs `package-lock.json`).
- Add runtime dep: `npm install axios`. Add dev dep: `npm install -D typescript vite`. Exact version: `npm install react@18.3.1`.
- Remove: `npm uninstall <pkg>`. Update: `npm update` / check `npm outdated`. Audit: `npm audit` / `npm audit fix`.
- Run package scripts: `npm run <script>` (defined in `package.json` "scripts"); run a binary without installing globally: `npx <tool>`.
- Alternatives (same registry): `pnpm add <pkg>` / `pnpm install` (fast, disk-efficient); `yarn add <pkg>` / `yarn install`.

## Java — Maven or Gradle
- Maven: deps go in `pom.xml` under `<dependencies>`. Build: `mvn package`; run tests: `mvn test`; skip tests: `mvn -DskipTests package`; just deps: `mvn dependency:resolve`. Artifacts cache in `~/.m2`.
- Gradle: deps in `build.gradle` `dependencies { implementation 'group:artifact:version' }`. Build: `./gradlew build`; run: `./gradlew run`; tests: `./gradlew test`. Use the wrapper `./gradlew` for a pinned Gradle version.
- A dependency coordinate is `groupId:artifactId:version`, e.g. `com.google.code.gson:gson:2.11.0` (search central at search.maven.org).

## System packages — apt (Ubuntu)
- `sudo apt update` then `sudo apt install -y <pkg>`. Search: `apt search <term>`. Info: `apt show <pkg>`. Remove: `sudo apt remove <pkg>`.
- Dev headers often end in `-dev` (e.g. `libssl-dev`). Build tools: `sudo apt install -y build-essential`.

## Other ecosystems (quick reference)
- Rust (Cargo): `cargo add <crate>` / `cargo build` / `cargo test`; deps in `Cargo.toml`.
- Go modules: `go get <module>` / `go mod tidy` / `go build ./...`; tracked in `go.mod`.
- Ruby (Bundler): add to `Gemfile`, `bundle install`. PHP (Composer): `composer require <pkg>`.

## Good practices
- Pin or range-bound versions in the manifest; commit the lockfile (`package-lock.json`, `poetry.lock`, `Cargo.lock`).
- Never hand-edit installed packages; change the manifest and reinstall.
- After adding a dep, run the build/tests to confirm it resolves. On Edison: `npm run build` for web, `python -m pytest` for the API.
