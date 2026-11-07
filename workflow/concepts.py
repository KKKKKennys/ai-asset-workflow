"""Native Codex image-tool dispatch; no API key handling or backend substitution."""
from pathlib import Path
import json, subprocess, os, uuid, re
from .core import WorkflowError, now, write_json, read_json, contained, image_suffix, digest


def ingest(project, receipt_path, data=None):
    receipt_path = Path(receipt_path).resolve()
    if project.root not in receipt_path.parents:
        raise WorkflowError('Concept receipt must be inside the private project directory')
    receipt = read_json(receipt_path)
    if receipt.get('schema_version') != 1:
        raise WorkflowError('Unsupported concept receipt schema')
    if receipt.get('approved') is True:
        raise WorkflowError('A worker cannot approve its generated concepts')
    if data is None:
        with project.transaction():
            return ingest(project, receipt_path, project.load())
    entries = receipt.get('assets', [])
    seen = set(); validated = []
    for entry in entries:
        key = entry['asset_id']; project.asset(data, key)
        if key in seen: raise WorkflowError('Duplicate asset in concept receipt')
        seen.add(key)
        if entry.get('approved') is True or entry.get('status') != 'generated':
            raise WorkflowError('Only generated, unapproved images can be ingested')
        path = contained(receipt_path.parent, entry['image_path'])
        image_suffix(path)
        sha = entry.get('sha256')
        if not isinstance(sha,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',sha):
            raise WorkflowError('Each generated image requires a recorded SHA256')
        if digest(path) != sha.lower():
            raise WorkflowError('Concept hash does not match receipt')
        validated.append((entry, path))
    if not validated: raise WorkflowError('No actual generated images in receipt')
    results = []
    for entry, path in validated:
        tool = entry.get('generation_tool', receipt.get('generation_tool', 'unreported'))
        c = project._register(data, entry['asset_id'], path, tool, entry.get('prompt', ''))
        c['reported_image_model'] = entry.get('image_model')
        c['generation_receipt'] = receipt_path.relative_to(project.root).as_posix()
        results.append(c)
    project.save(data, 'concept_batch_received', details={'assets': sorted(seen)})
    return results


def generate(project, executable, model='gpt-6-astra', timeout=1200, asset_id=None):
    if timeout < 1: raise WorkflowError('Timeout must be positive')
    with project.transaction():
        data = project.load()
        targets = [project.asset(data, asset_id)] if asset_id else [a for a in data['assets'] if a['status'] == 'needs_concept']
        if not targets: raise WorkflowError('No new concept tasks; choose --asset for an explicit variant')
        if any(a['status'] in ('running', 'generating_concept', 'failed') for a in targets):
            raise WorkflowError('Resolve active or failed tasks first')
        job = contained(project.root, 'concept-jobs/' + uuid.uuid4().hex[:12]); job.mkdir(parents=True)
        outputs = job / 'outputs'; outputs.mkdir()
        receipt = job / 'result.json'
        brief = {'style': data['style'], 'assets': [{k:a[k] for k in ('id','name','brief')} for a in targets]}
        prompt = '''Generate one real design-reference image per asset below with the built-in image_gen tool.
Use one call per asset, shared style, full uncropped 3/4 product view, neutral studio background,
readable geometry and physically credible supports. Inspect the actual images. No Python/SVG
placeholders, no API fallback, no Blender, no global settings changes, no publication.
Copy outputs only to OUTPUT_DIR and preserve originals. Write RECEIPT JSON:
{"schema_version":1,"approved":false,"generation_tool":"actual tool name","assets":[
{"asset_id":"...","image_path":"outputs/asset.png","status":"generated","approved":false,
"prompt":"actual full prompt","generation_tool":"actual tool name","image_model":null,"sha256":"actual hash"}]}
Image paths are relative to this receipt directory. Only record generated when an actual image
exists. Keep image_model null if not exposed; never infer it from the execution model.
All images remain pending human review. Stop and report if generation fails; do not silently retry.
'''.replace('OUTPUT_DIR', str(outputs)).replace('RECEIPT', str(receipt))
        prompt += '\nAsset brief:\n' + json.dumps(brief, ensure_ascii=False, indent=2)
        (job / 'prompt.txt').write_text(prompt, encoding='utf-8')
        prior = {a['id']:a['status'] for a in targets}
        for a in targets:
            a['status']='generating_concept'
            a['attempts'].append({'job_id':job.name,'stage':'concept','model_requested':model,'started_at':now()})
        project.save(data,'concept_worker_started',details={'job_id':job.name,'assets':list(prior)})
        proc = None
        try:
            with (job/'events.jsonl').open('w',encoding='utf-8') as out,(job/'stderr.txt').open('w',encoding='utf-8') as err:
                proc=subprocess.Popen([str(executable),'exec','-m',model,'--json','--sandbox','workspace-write',
                    '--skip-git-repo-check','-C',str(project.root),'-o',str(job/'last-message.txt'),'-'],
                    stdin=subprocess.PIPE,stdout=out,stderr=err,text=True,encoding='utf-8',shell=False,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                proc.communicate(prompt,timeout=timeout)
            if proc.returncode != 0 or not receipt.is_file():
                raise WorkflowError('Concept worker failed or produced no receipt; inspect private logs')
            report=read_json(receipt)
            if {e['asset_id'] for e in report.get('assets',[])} != set(prior):
                raise WorkflowError('Concept receipt does not cover exactly the requested assets')
            for a in targets:a['status']=prior[a['id']]
            result=ingest(project,receipt,data)
            for a in targets:a['attempts'][-1].update({'finished_at':now(),'exit_code':0})
            project.save(data,'concept_worker_finished',details={'job_id':job.name})
            return result
        except BaseException as exc:
            if proc and proc.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
                else:proc.kill()
                proc.wait()
            for a in targets:
                a['status']='failed';a['last_failed_stage']='concept';a['last_error']=str(exc)
                a['attempts'][-1].update({'finished_at':now(),'error':str(exc)})
            project.save(data,'concept_worker_failed',details={'job_id':job.name,'reason':str(exc)})
            raise
