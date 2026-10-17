#!/usr/bin/env python3
"""
Einfacher Custom-Agent-Runner für AGORIS.
Mit diesem Tool kann man schnell eigene Python-Dateien in der Sandbox testen.
"""

import os
import sys
import tempfile
from agoris.policy import Policy
from agoris.launcher import run_snippet
from agoris.audit import AuditLog
from agoris import style

def run_custom(file_path: str, policy_name: str = "minimal", timeout: float = 30.0):
    """Führt eine Python-Datei in der AGORIS-Sandbox aus."""
    if not os.path.exists(file_path):
        print(style.error(f"Datei nicht gefunden: {file_path}"))
        return 1
    
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    print(style.header(f"Starte {os.path.basename(file_path)} in Sandbox"))
    print(style.info(f"Policy: {policy_name} | Timeout: {timeout}s"))
    print(style.dim_text("-" * 60))
    
    policy = Policy.load(policy_name)
    
    with tempfile.TemporaryDirectory(prefix="agoris_custom_") as tmpdir:
        run_dir = os.path.join(tmpdir, "run")
        os.makedirs(run_dir)
        audit = AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=False)
        
        result = run_snippet(code, policy, run_dir, audit=audit, 
                            timeout=timeout, label="custom")
        audit.close()
        
        print(result.stdout.rstrip() if result.stdout else style.dim_text("(keine Ausgabe)"))
        if result.stderr:
            print(style.error("STDERR:"))
            print(result.stderr[:2000])
        
        print(style.dim_text("-" * 60))
        status = style.success("ERFOLG") if result.exit_code == 0 else style.error(f"FEHLER ({result.exit_code})")
        print(f"Status: {status} | Dauer: {result.seconds:.2f}s")
        print(f"Audit: {audit.path}")
    
    return 0

def main():
    if len(sys.argv) < 2:
        print(style.header("Custom-Agent-Runner für AGORIS"))
        print("Verwendung:")
        print("  python3 custom_runner.py mein_agent.py")
        print("  python3 custom_runner.py mein_agent.py research 60")
        print()
        print("Beispiel:")
        print("  python3 custom_runner.py sample_agent.py")
        return 1
    
    file_path = sys.argv[1]
    policy = sys.argv[2] if len(sys.argv) > 2 else "minimal"
    timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    
    return run_custom(file_path, policy, timeout)

if __name__ == "__main__":
    sys.exit(main())
