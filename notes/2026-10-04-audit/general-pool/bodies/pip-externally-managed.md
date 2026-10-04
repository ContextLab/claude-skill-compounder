Install into a virtual environment, not into this Python. It is marked as managed by the
OS or by Homebrew (PEP 668), pip refused, and nothing was installed.

- A library the project needs: `python3 -m venv .venv && .venv/bin/python -m pip install
  <package>`, then run the code with `.venv/bin/python`. Call the environment by path:
  activating it in one Bash call does not carry to the next.
- A command-line application: `pipx install <app>`.
- Retrying with `--break-system-packages` (or `--user` with it) is not the fix: it
  installs into the interpreter the package manager owns and can break what that manager
  installed. Use it only when the user asks for it.
