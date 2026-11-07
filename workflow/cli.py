import argparse, json, sys, subprocess
from pathlib import Path
from .core import Project, WorkflowError, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description='Human-reviewed AI asset production coordinator')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['init', 'status', 'generate-concepts', 'ingest-concepts', 'register', 'review', 'approve', 'packet', 'run-codex', 'record-result', 'retry', 'accept-delivery']:
        p = sub.add_parser(command); p.add_argument('--project', required=True)
        if command not in ('init', 'status', 'review', 'generate-concepts', 'ingest-concepts'): p.add_argument('--asset', required=True)
        if command == 'generate-concepts': p.add_argument('--asset')
        if command == 'ingest-concepts': p.add_argument('--receipt', required=True)
        if command == 'init': p.add_argument('--brief', required=True)
        if command == 'register':
            p.add_argument('--image', required=True); p.add_argument('--source', required=True); p.add_argument('--prompt-file')
        if command == 'approve': p.add_argument('--candidate', required=True)
        if command in ('approve', 'accept-delivery'): p.add_argument('--decision-note', required=True)
        if command in ('packet', 'run-codex', 'record-result'): p.add_argument('--stage', choices=['model', 'deliver'], required=True)
        if command == 'record-result': p.add_argument('--receipt', required=True)
        if command in ('run-codex', 'generate-concepts'):
            p.add_argument('--codex', required=True); p.add_argument('--model', default='gpt-6-astra'); p.add_argument('--timeout', type=int, default=1200)
    a = parser.parse_args(argv); project = Project(a.project)
    try:
        if a.command == 'init': result = project.init(read_json(a.brief))
        elif a.command == 'status': result = project.load()
        elif a.command == 'review': result = project.review()
        elif a.command == 'generate-concepts':
            from .concepts import generate
            result = generate(project, a.codex, a.model, a.timeout, a.asset)
        elif a.command == 'ingest-concepts':
            from .concepts import ingest
            result = ingest(project, a.receipt)
        elif a.command == 'register': result = project.register(a.asset, a.image, a.source, Path(a.prompt_file).read_text(encoding='utf-8') if a.prompt_file else '')
        elif a.command == 'approve': result = project.approve(a.asset, a.candidate, a.decision_note)
        elif a.command == 'packet': result = project.packet(a.asset, a.stage)
        elif a.command == 'run-codex': result = project.run_codex(a.asset, a.stage, a.codex, a.model, a.timeout)
        elif a.command == 'record-result': result = project.record(a.asset, a.stage, a.receipt)
        elif a.command == 'retry': result = project.retry(a.asset)
        elif a.command == 'accept-delivery': result = project.accept_delivery(a.asset, a.decision_note)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, indent=2)); return 0
    except (WorkflowError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
