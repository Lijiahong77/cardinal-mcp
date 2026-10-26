"""Independent candidate replay. Usage: python3 -B replay.py --root NEW_DIRECTORY.
Creates only that new directory; no git add/commit; never opens sockets.
"""
import argparse,pathlib,json,gzip,base64,subprocess,hashlib,stat,sys
H=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(H.parent));import replay_osc

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True,type=pathlib.Path);a=ap.parse_args();assert not a.root.exists(),a.root
 rcm=a.root/'plugins/rcm-modules';rcm.mkdir(parents=True);fixture=json.loads((H/'after16.json').read_text());rows=[]
 for rel,row in fixture['files'].items():
  p=rcm/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.decompress(base64.b64decode(row['gzip_base64'])));p.chmod(0o644)
 subprocess.run(['git','-C',str(rcm),'init','-q'],check=True)
 def state():return {rel:dict(sha256=hashlib.sha256((rcm/rel).read_bytes()).hexdigest(),mode=stat.S_IMODE((rcm/rel).stat().st_mode)) for rel in fixture['files']}
 pre=state()
 for opts,expect in [({'dry_run':True},'would_apply'),({},'applied'),({},'skipped')]:
  status,detail=replay_osc.apply_one(str(a.root),str(H),'candidate.patch','isolated candidate17','plugins/rcm-modules',**opts);assert status==expect,(status,detail);rows.append(dict(status=status,detail=detail,state=state()));target='before_sha256' if expect=='would_apply' else 'candidate_sha256';assert all(v['sha256']==fixture['files'][rel][target] and v['mode']==0o644 for rel,v in state().items());assert not (rcm/'.git/index').exists()
 for flags in [['--check','-R','-v'],['-R','-v']]:
  p=subprocess.run(['git','-C',str(rcm),'apply',*flags,str(H/'candidate.patch')],capture_output=True,text=True);assert p.returncode==0 and 'Skipped' not in p.stderr,(p.returncode,p.stderr)
 assert state()==pre;assert not (rcm/'.git/index').exists()
 status,detail=replay_osc.apply_one(str(a.root),str(H),'candidate.patch','isolated candidate17 reapply','plugins/rcm-modules')
 assert status=='applied',(status,detail);rows.append(dict(status=status,detail=detail,state=state()))
 assert all(v['sha256']==fixture['files'][rel]['candidate_sha256'] and v['mode']==0o644 for rel,v in state().items())
 assert not (rcm/'.git/index').exists()
 out=dict(stages=rows,reverse_bytes_modes=True,reapply_bytes_modes=True,index_absent_unchanged=True);(a.root/'replay-results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
