"""Installer self-check: the engine imports and both models are ready. Exit 0 if so.

Kept as a module (python -m server.selfcheck) because Windows PowerShell 5.1 strips the inner
double quotes from one-line `python -c "..."` arguments.
"""
import sys


def main():
    from . import app, models  # noqa: F401  (importing app proves the whole engine loads)
    caps = models.capabilities()
    problems = [name for name in ('transcription', 'separation') if not caps[name]['configured']]
    for name in problems:
        print(f'    {name} is not ready: {caps[name].get("detail", "")}')
    if problems:
        return 1
    print(f'    Separation and transcription ready. Graphics card usable: {"yes" if caps["gpu"]["available"] else "no"}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
