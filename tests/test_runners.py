"""Synthetic worker protocol tests. These do not call Codex or Blender."""
import json, subprocess, tempfile, unittest, struct, zlib
from pathlib import Path
from unittest.mock import Mock, patch
from workflow.core import Project, WorkflowError, digest
from workflow.concepts import generate

def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
PNG=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x80\x90\xa0'))+chunk(b'IEND',b'')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=Project(self.root/'project.json')
        self.project.init({'name':'Synthetic fixture','style':'test only','assets':[{'id':'box','name':'Box','brief':'test fixture'}]})

    def fake(self):
        proc=Mock();proc.returncode=0;proc.poll.return_value=0
        return proc

    def test_concept_result_registers_without_approval(self):
        proc=self.fake()
        def produce(*args,**kwargs):
            job=next((self.root/'concept-jobs').iterdir());image=job/'outputs/box.png';image.write_bytes(PNG)
            (job/'result.json').write_text(json.dumps({'schema_version':1,'approved':False,'assets':[
                {'asset_id':'box','status':'generated','approved':False,'image_path':'outputs/box.png','sha256':digest(image),'generation_tool':'synthetic-mock','image_model':None}]}),encoding='utf-8')
        proc.communicate.side_effect=produce
        with patch('workflow.concepts.subprocess.Popen',return_value=proc):
            result=generate(self.project,'mock-codex')
        asset=self.project.load()['assets'][0]
        self.assertEqual(len(result),1);self.assertEqual(asset['status'],'concept_review')
        self.assertIsNone(asset['approval'])
        with self.assertRaises(WorkflowError):self.project.packet('box','model')

    def test_zero_exit_without_receipt_is_failure_and_can_retry(self):
        with patch('workflow.concepts.subprocess.Popen',return_value=self.fake()):
            with self.assertRaises(WorkflowError):generate(self.project,'mock-codex')
        self.assertEqual(self.project.load()['assets'][0]['status'],'failed')
        self.project.retry('box')
        self.assertEqual(self.project.load()['assets'][0]['status'],'needs_concept')
        self.assertFalse(self.project.path.with_suffix('.json.lock').exists())

    def test_unapproved_model_does_not_spawn_worker(self):
        with patch('workflow.core.subprocess.Popen') as spawn:
            with self.assertRaises(WorkflowError):self.project.run_codex('box','model','mock-codex')
        spawn.assert_not_called()

    def test_model_timeout_records_failure_and_releases_lock(self):
        image=self.root/'reference.png';image.write_bytes(PNG)
        c=self.project.register('box',image,'synthetic-mock');self.project.approve('box',c['id'],'Synthetic test approval, not a real user approval')
        proc=self.fake();proc.pid=999999;proc.poll.return_value=None
        proc.communicate.side_effect=subprocess.TimeoutExpired('mock-codex',1)
        with patch('workflow.core.subprocess.Popen',return_value=proc),patch('workflow.core.subprocess.run') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):self.project.run_codex('box','model','mock-codex',timeout=1)
        a=self.project.load()['assets'][0]
        self.assertEqual(a['status'],'failed');self.assertEqual(a['last_failed_stage'],'model')
        self.assertFalse(self.project.path.with_suffix('.json.lock').exists())
        self.project.retry('box');self.assertEqual(self.project.load()['assets'][0]['status'],'approved')


if __name__=='__main__':unittest.main()
