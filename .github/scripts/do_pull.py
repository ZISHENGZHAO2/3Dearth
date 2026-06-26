#!/usr/bin/env python3
import subprocess, sys
r = subprocess.run(['git', 'pull'], cwd=sys.argv[1] if len(sys.argv)>1 else '.', capture_output=True, text=True)
print(r.stdout)
if r.stderr: print('STDERR:', r.stderr[:500])
print('Exit:', r.returncode)