#!/usr/bin/env python3
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(script): subprocess.run([sys.executable,str(ROOT/'scripts'/script)],check=True)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); a=ap.parse_args()
    if not (ROOT/'data'/'concerts.json').exists(): run('seed_data.py')
    if not a.offline:
        run('sync_cureguide.py'); run('sync_setlistfm.py')
    run('build_site.py'); run('export_excel.py')
if __name__=='__main__': main()
