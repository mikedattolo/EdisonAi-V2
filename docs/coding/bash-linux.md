# Bash & Linux Command Reference (Ubuntu)

Edison runs on Ubuntu Linux. These are the everyday shell commands for navigating, inspecting, and operating the box.

## Files & directories
- `pwd` print dir; `ls -la` list (incl. hidden + details); `cd <dir>`; `cd -` previous dir.
- `cat file`, `less file` (q to quit), `head -n 40 file`, `tail -n 40 file`, `tail -f log` (follow).
- `mkdir -p a/b/c`, `cp -r src dst`, `mv a b`, `rm file`, `rm -rf dir` (careful — irreversible), `touch file`.
- `find . -name "*.py"`, `find . -type f -newermt "-1 day"`. `du -sh *` sizes; `df -h` disk free.
- `chmod +x script.sh` make executable; `chmod 644 file`; `chown user:group file`.

## Searching text
- `grep -rn "pattern" .` recursive with line numbers; `-i` case-insensitive; `--include="*.ts"`; `-E` extended regex; `-l` filenames only; `--exclude-dir=node_modules`.
- `ripgrep` (`rg`) is faster if installed: `rg "pattern" -t py`.
- Pipes & redirection: `cmd | grep x`, `cmd > out.txt` (overwrite), `>>` append, `2>&1` merge stderr, `cmd < in.txt`.

## Processes & resources
- `ps -eo pid,comm,args | grep name`; `pgrep -af name`; `top` / `htop` live; `kill <pid>`, `kill -9 <pid>` force.
- `nvidia-smi` GPU usage/memory; `free -h` RAM; `uptime` load.
- Background a long job: `cmd &`; detach so it survives logout: `setsid cmd </dev/null >log 2>&1 &` or `nohup cmd &`.

## systemd (services) — Edison uses USER services
- First: `export XDG_RUNTIME_DIR=/run/user/$(id -u)`.
- `systemctl --user status|start|stop|restart <unit>.service`; list: `systemctl --user list-units 'edison*'`.
- Logs: `journalctl --user -u <unit>.service -n 100 --no-pager` (`-f` to follow).
- Run a one-off in a transient unit (survives caller exit): `systemd-run --user --on-active=1 <cmd>`.

## Packages (apt)
- `sudo apt update`; `sudo apt install -y <pkg>`; `sudo apt remove <pkg>`; `apt search <term>`; `apt show <pkg>`.

## Networking & misc
- `curl -s URL` fetch; `curl -X POST URL -H "Content-Type: application/json" -d '{"k":"v"}'`; `-o file` save; `-w "%{http_code}"` show status.
- `ss -tlnp` listening ports (e.g. confirm :8000 / :5173). `ping host`. `ip a` interfaces.
- Env vars: `export NAME=value`; read `$NAME`; inline `NAME=value cmd`. `which <cmd>` find a binary.
- Archives: `tar czf out.tgz dir/` create, `tar xzf out.tgz` extract; `zip -r out.zip dir`, `unzip out.zip`.

## Safety
- Double-check `rm -rf` targets and paths with spaces (quote them). Prefer relative, scoped paths.
- Don't pipe untrusted scripts straight into a shell. Read scripts before running.
