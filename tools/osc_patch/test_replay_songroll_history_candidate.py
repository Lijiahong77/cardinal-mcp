"""Offline history/UI regressions; original method IDs retained after group-16 integration.
Git writes only scratch fixtures. C++ tests require WSL g++11 + real Jansson; missing
prerequisites FAIL, never skip. Extracted real methods run with documented serial shells.
"""
import base64,gzip,hashlib,importlib.util,json,os
from pathlib import Path
import shutil,subprocess,tempfile,unittest
import replay_osc as replay
import test_replay_safety as safety

HERE=Path(__file__).resolve().parent
HARNESS=HERE/'songroll_history_harness'
FIXTURE=json.loads((HARNESS/'after15.json').read_text())
NAME='candidate.patch'
EVIDENCE=[]

def digest(b):return hashlib.sha256(b).hexdigest()
def linux(p):
    text=Path(p).resolve().as_posix()
    if len(text)>2 and text[1]==':':return '/mnt/'+text[0].lower()+text[2:]
    return text

def execute_harness(reference,out,cases=None):
    args=['python3','-B',linux(HARNESS/'run.py'),'--reference',linux(reference),'--out',linux(out)]
    for case in cases or []:args+=['--case',case]
    command=['wsl.exe','-d','Ubuntu-26.04','--','env','JANSSON_INCLUDE_DIR='+os.environ.get('JANSSON_INCLUDE_DIR',''),*args] if os.name=='nt' else args
    p=subprocess.run(command,capture_output=True,timeout=300)
    result=json.loads((out/'results.json').read_text()) if (out/'results.json').exists() else None
    row={'command':command,'rc':p.returncode,'stdout':p.stdout.decode('utf8','replace'),'stderr':p.stderr.decode('utf8','replace'),'results':result};EVIDENCE.append(row)
    return row

class CandidateReplay(unittest.TestCase):
    def git(self,*args):
        p=subprocess.run(['git','-C',str(self.root),*args],capture_output=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        return p.stdout.decode('utf8','replace')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='songroll-replay-',dir=safety.SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/'repo';self.root.mkdir()
        self.git('init','-q')
        self.applyroot=self.root/'plugins/rcm-modules';self.applyroot.mkdir(parents=True)
        for rel,row in FIXTURE['files'].items():
            p=self.applyroot/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.decompress(base64.b64decode(row['gzip_base64'])))
        self.git('init','-q',str(self.applyroot))
        p=subprocess.run(['git','-C',str(self.applyroot),'config','core.autocrlf','false'],capture_output=True);self.assertEqual(p.returncode,0)
        p=subprocess.run(['git','-C',str(self.applyroot),'add','--','src'],capture_output=True);self.assertEqual(p.returncode,0)
    def state(self):return {p:(self.applyroot/p).read_bytes() for p in FIXTURE['files']}
    def apply(self,**kwargs):return replay.apply_one(str(self.root),str(HARNESS),NAME,'candidate history/ui','plugins/rcm-modules',**kwargs)
    def test_candidate_not_registered_and_manifest(self):
        # Historical method ID retained; candidate.patch itself is still not registered.
        self.assertEqual(len(replay.PATCHES),17)
        self.assertFalse(any(x[0]==NAME for x in replay.PATCHES))
        self.assertEqual(replay.PATCHES[15][0],'16-songroll-history-ui.patch')
        self.assertEqual(replay.PATCHES[15][2],'plugins/rcm-modules')
        self.assertEqual((HERE/'patches'/replay.PATCHES[15][0]).read_bytes(),(HARNESS/NAME).read_bytes())
        self.assertEqual(replay.EXPECTED_ENDPOINTS,33);self.assertEqual(len(replay.VERIFY_MARKS),36)
        self.assertEqual(digest((HARNESS/NAME).read_bytes()),FIXTURE['patch_sha256'])
        self.assertEqual(FIXTURE['apply_root'],'plugins/rcm-modules')
    def test_fixed_after15_dry_apply_skip_reverse_bytes_modes_index(self):
        before=self.state();index=self.applyroot/'.git/index';indexbytes=index.read_bytes()
        self.assertEqual({p:digest(b) for p,b in before.items()},{p:r['before_sha256'] for p,r in FIXTURE['files'].items()})
        records=[]
        for kwargs,expected in [({'dry_run':True},'would_apply'),({},'applied'),({},'skipped')]:
            status,detail=self.apply(**kwargs);records.append({'status':status,'detail':detail});self.assertEqual(status,expected,detail)
            expected_bytes=before if expected=='would_apply' else {p:(HARNESS/'reference'/Path(p).name).read_bytes() for p in before}
            self.assertEqual(self.state(),expected_bytes);self.assertEqual(index.read_bytes(),indexbytes)
        for args in [['apply','--check','-R','-v'],['apply','-R','-v']]:
            result=replay.run_git(args+[str(HARNESS/NAME)],str(self.applyroot));records.append(result);self.assertEqual(result['returncode'],0,result);self.assertNotIn('Skipped patch',result['stdout']+result['stderr'])
        self.assertEqual(self.state(),before);self.assertEqual(index.read_bytes(),indexbytes)
        modes=replay.run_git(['ls-files','-s'],str(self.applyroot));self.assertEqual(modes['returncode'],0)
        self.assertEqual({line.split()[0] for line in modes['stdout'].splitlines()},{'100644'})
        EVIDENCE.append({'fixture_replay':records,'index_unchanged':True,'source_mode':'100644','reverse_exact_bytes':True})
    def test_partial_installation_conflict(self):
        self.assertEqual(self.apply()[0],'applied')
        p=next(iter(FIXTURE['files']));(self.applyroot/p).write_bytes(gzip.decompress(base64.b64decode(FIXTURE['files'][p]['gzip_base64'])))
        before=self.state();self.assertEqual(self.apply()[0],'conflict');self.assertEqual(self.state(),before)
    def test_wrong_root_conflict(self):
        before=self.state();status,detail=replay.apply_one(str(self.root),str(HARNESS),NAME,'wrong root','');self.assertEqual(status,'conflict',detail);self.assertEqual(self.state(),before)
    def test_missing_repository_conflict(self):
        (self.applyroot/'.git').rename(self.applyroot/'.git-detached-fixture')
        before=self.state();self.assertEqual(self.apply()[0],'conflict');self.assertEqual(self.state(),before);self.assertFalse((self.applyroot/'.git').exists())
    def test_fixture_and_saved_source_integrity(self):
        manifest=json.loads((HARNESS/'sources.json').read_text())
        self.assertEqual({p.name:digest(p.read_bytes()) for p in (HARNESS/'reference').iterdir() if p.is_file()},manifest)
        for p,r in FIXTURE['files'].items():
            self.assertEqual(digest((HARNESS/'reference'/Path(p).name).read_bytes()),r['candidate_sha256'])
            self.assertEqual(digest(gzip.decompress(base64.b64decode(r['gzip_base64']))),r['before_sha256'])
    def test_before_sources_fail_snapshot_contract(self):
        raw=self.base/'raw';shutil.copytree(HARNESS/'reference',raw)
        for p,r in FIXTURE['files'].items():(raw/Path(p).name).write_bytes(gzip.decompress(base64.b64decode(r['gzip_base64'])))
        row=execute_harness(raw,self.base/'raw-result',['snapshot_pattern','snapshot_repeats','snapshot_clock'])
        self.assertEqual(row['rc'],1,row)
        self.assertEqual(row['results']['compile']['rc'],0,row)
        for case in row['results']['cases']:
            self.assertEqual(case['rc'],1,case);self.assertIn('history snapshots must be complete Module JSON',case['stdout']);self.assertEqual(case['stderr'],'')

spec=importlib.util.spec_from_file_location('songroll_candidate_runner',HARNESS/'run.py')
assert spec is not None and spec.loader is not None
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class SerialCpp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='songroll-cpp-',dir=safety.SCRATCH);cls.addClassCleanup(cls.tmp.cleanup)
        cls.row=execute_harness(HARNESS/'reference',Path(cls.tmp.name)/'out')
        if cls.row['results'] is None or cls.row['results']['compile']['rc']!=0:raise AssertionError(cls.row)
        cls.cases={r['id']:r for r in cls.row['results']['cases']}
        if len(cls.cases)!=len(runner.CASES):raise AssertionError('missing/duplicate C++ scenarios')
def behavior(case):
    def check(self):
        row=self.cases[case];self.assertEqual(row['rc'],0,row);self.assertEqual(row['stdout'],'PASS '+case+'\n');self.assertEqual(row['stderr'],'',row)
    return check
for case in runner.CASES:setattr(SerialCpp,'test_'+case,behavior(case))
if __name__=='__main__':unittest.main(verbosity=2)
