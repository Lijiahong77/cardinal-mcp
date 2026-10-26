"""Offline candidate17/B1: 52 real-source cases + 6 artifacts, 58 unique methods.
No candidate-name registration or sockets. Twelve B1 cases extend the original
46 methods without counting C++ or TSan executions as separate unittest methods.
The original16 22-case evidence remains immutable. This suite repeats those cases
against17; preserve_unrelated explicitly permits stop-first per user authorization.
"""
import pathlib,importlib.util,json,hashlib,unittest,subprocess,os,tempfile,gzip,base64
HERE=pathlib.Path(__file__).parent;H=HERE/'songroll_stopfirst_harness'
spec=importlib.util.spec_from_file_location('stopfirst_harness_runner',H/'run.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
EVIDENCE={}
class SourceCases(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  global EVIDENCE
  if os.name=='nt':
   out=pathlib.Path(os.environ['TMPDIR'])/'songroll-stopfirst-regression';out.mkdir(exist_ok=True)
   # Windows native persistent scratch maps to /mnt/d; real WSL C++11/Jansson execution.
   linux='/mnt/'+str(out).replace('\\','/')[0].lower()+str(out).replace('\\','/')[2:]
   script='/mnt/'+str(H/'run.py').replace('\\','/')[0].lower()+str(H/'run.py').replace('\\','/')[2:]
   p=subprocess.run(['wsl.exe','-d','Ubuntu-26.04','--','env','JANSSON_INCLUDE_DIR='+os.environ.get('JANSSON_INCLUDE_DIR',''),'python3','-B',script,'--out',linux],capture_output=True,timeout=180)
  else:
   out=pathlib.Path(tempfile.mkdtemp(prefix='songroll-stopfirst-'));p=subprocess.run(['python3','-B',str(H/'run.py'),'--out',str(out)],capture_output=True,timeout=180)
  EVIDENCE=json.loads((out/'results.json').read_text());EVIDENCE['launcher_rc']=p.returncode
  assert EVIDENCE['compile']['rc']==0,(out/'compile.log').read_text()
  cls.rows={r['id']:r for r in EVIDENCE['cases']};assert set(cls.rows)==set(runner.CASES)
def make_case(case):
 def test(self):
  row=self.rows[case];self.assertEqual(row['rc'],0,row);self.assertEqual(row['stderr'],'',row)
 test.__name__='test_cpp_'+case;return test
for case in runner.CASES:setattr(SourceCases,'test_cpp_'+case,make_case(case))
class CandidateArtifacts(unittest.TestCase):
 def test_input_hashes(self):
  expected=json.loads((H/'sources.json').read_text());self.assertEqual(expected,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (H/'reference').iterdir() if p.is_file()})
 def test_incremental_after16(self):
  fixture=json.loads((H/'after16.json').read_text());self.assertEqual(fixture['apply_root'],'plugins/rcm-modules');self.assertEqual(len(fixture['files']),7)
  for rel,r in fixture['files'].items():self.assertEqual(hashlib.sha256(gzip.decompress(base64.b64decode(r['gzip_base64']))).hexdigest(),r['before_sha256']);self.assertEqual(hashlib.sha256((H/'reference'/pathlib.Path(rel).name).read_bytes()).hexdigest(),r['candidate_sha256'])
 def test_not_registered(self):
  import replay_osc
  self.assertEqual(len(replay_osc.PATCHES),17);self.assertFalse(any(x[0]=='17-songroll-stopfirst-candidate.patch' for x in replay_osc.PATCHES));self.assertFalse((HERE/'patches/17-songroll-stopfirst-candidate.patch').exists())
  self.assertEqual(replay_osc.PATCHES[-1][0],'17-songroll-stopfirst.patch');self.assertEqual(replay_osc.PATCHES[-1][2],'plugins/rcm-modules');self.assertEqual(sum(x[0]=='17-songroll-stopfirst.patch' for x in replay_osc.PATCHES),1)
  self.assertEqual((HERE/'patches/17-songroll-stopfirst.patch').read_bytes(),(H/'candidate.patch').read_bytes())
 def test_no_ui_output_writer(self):
  files=['PatternControlWidget.cpp','RepeatControlWidget.cpp','ClockDivControlWidget.cpp','PatternControllerSlice.cpp','RollArea.cpp']
  for f in files:self.assertNotIn('outputs[',(H/'reference'/f).read_text())
  cpp=(H/'reference/SongRollModule.cpp').read_text()
  for sig in ['void SongRollModule::stopFirst','void SongRollModule::enterSection','void SongRollModule::resetState','void SongRollModule::dataFromJson']:self.assertNotIn('outputs[',runner.extract(cpp,sig))
 def test_no_engine_lock_inversion(self):
  for f in ['SongRollModule.cpp','PatternControlWidget.cpp','RepeatControlWidget.cpp','ClockDivControlWidget.cpp','PatternControllerSlice.cpp','RollArea.cpp']:self.assertNotIn('APP->engine',(H/'reference'/f).read_text())
 def test_no_new_port_or_endpoint(self):
  fixture=json.loads((H/'after16.json').read_text());pre=gzip.decompress(base64.b64decode(fixture['files']['src/SongRoll/SongRollModule.hpp']['gzip_base64'])).decode();post=(H/'reference/SongRollModule.hpp').read_text()
  for name in ['ParamIds','InputIds','OutputIds','LightIds']:self.assertEqual(runner.extract(pre,'enum '+name),runner.extract(post,'enum '+name))
if __name__=='__main__':unittest.main()
