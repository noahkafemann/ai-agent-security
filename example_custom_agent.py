#!/usr/bin/env python3
"""Beispiel für einen benutzerdefinierten Agenten für AGORIS.

Dieser Agent demonstriert das Protokoll, das ein benutzerdefinierter Agent
implementieren muss, um in der AGORIS-Sandbox zu laufen.

Das Protokoll (über stdin/stdout, JSON Lines):
1. Empfängt config-Nachricht vom Wirt (op=config)
2. Sendet ready-Nachricht mit Agenten-Info
3. Schleife:
   - Sendet llm_request mit messages und verfügbaren tools
   - Wartet auf llm_result vom Wirt
   - Parst die Antwort
   - Ruft Tool auf (über eigenes Tool-System oder direkt)
   - Sendet tool-Ergebnis
   - Bei finish: bricht ab
4. Sendet result mit Endergebnis

Ein echter Agent (OpenCode, Bionic, etc.) würde hier seine eigene Logik
implementieren, muss aber dasselbe Protokoll sprechen.
"""

import json
import os
import sys
from typing import Any, Dict, List


class Channel:
    """Einfacher JSON-Lines-Kanal über stdin/stdout."""
    
    def __init__(self):
        self._in = sys.stdin
        self._out = sys.stdout
    
    def send(self, message: Dict[str, Any]) -> None:
        self._out.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._out.flush()
    
    def recv(self) -> Dict[str, Any] | None:
        line = self._in.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return self.recv()
        return json.loads(line)
    
    def wait_for(self, op: str) -> Dict[str, Any] | None:
        while True:
            msg = self.recv()
            if msg is None:
                return None
            if msg.get("op") == op:
                return msg


def main() -> int:
    channel = Channel()
    
    # 1. Config empfangen
    config = channel.recv()
    if not config or config.get("op") != "config":
        print("Fehler: Keine gültige Config empfangen", file=sys.stderr)
        return 1
    
    task = config.get("task", "")
    policy = config.get("policy", {})
    tools_config = policy.get("tools", {})
    available_tools = tools_config.get("enabled", ["read_file", "write_file", "list_dir", "run_python", "fetch_url", "finish"])
    
    # 2. Ready senden
    channel.send({
        "event": "ready",
        "pid": os.getpid(),
        "uid": os.getuid(),
        "tools": available_tools,
        "info": {
            "agent": "example_custom_agent",
            "version": "1.0",
            "protocol": "agoris/1.0",
        }
    })
    
    # 3. Agenten-Loop
    messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
    step = 0
    max_steps = int(policy.get("model", {}).get("max_steps", 10))
    answer = ""
    stopped = "step_limit"
    
    while step < max_steps:
        step += 1
        
        # LLM Request senden
        channel.send({
            "event": "llm_request",
            "id": f"s{step}",
            "messages": messages,
            "tools": available_tools,
        })
        
        # Auf Antwort warten
        response = channel.wait_for("llm_result")
        if response is None:
            stopped = "host_disconnected"
            break
        
        reply = response.get("response", {})
        text = reply.get("text", "")
        
        # Einfaches Parsing (wie in model.py _parse_reply)
        import re
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        
        try:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start >= 0 and end > start:
                decision = json.loads(cleaned[start:end+1])
            else:
                decision = {"thought": cleaned[:400], "tool": "finish", "args": {"answer": cleaned}}
        except json.JSONDecodeError:
            decision = {"thought": cleaned[:400], "tool": "finish", "args": {"answer": cleaned}}
        
        thought = decision.get("thought", "")
        tool = decision.get("tool", "finish")
        args = decision.get("args", {}) or {}
        
        channel.send({"event": "log", "step": step, "message": f"{thought} -> {tool}"})
        
        # Tool ausführen (einfache Implementierung für Demo)
        result = execute_tool(tool, args)
        channel.send({"event": "tool", "call": result})
        
        messages.append({"role": "assistant", "content": text[:2000]})
        messages.append({
            "role": "user",
            "content": f"Werkzeug '{tool}' ergab: {str(result)[:1500]}",
        })
        
        if tool == "finish" and result.get("ok"):
            answer = str(result.get("answer", ""))
            stopped = "finish"
            break
        if tool == "finish":
            stopped = "finish_mit_fehler"
            break
    
    # 4. Ergebnis senden
    channel.send({
        "event": "result",
        "answer": answer,
        "stopped": stopped,
        "steps": step,
        "dateien": collect_files(),
        "metrics": {
            "wall_seconds": 0,
            "tool_calls": step,
            "tools_blocked": 0,
            "max_steps": max_steps,
        },
    })
    
    return 0


def execute_tool(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Führt ein Tool aus. In einem echten Agenten würde dies die echte Logik sein."""
    import subprocess
    import os
    
    try:
        if tool == "read_file":
            path = args.get("path", ".")
            full_path = os.path.join("/work", path.lstrip("/"))
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read(100 * 1024)  # max 100KB
            return {"tool": "read_file", "ok": True, "answer": content, "args": args}
        
        elif tool == "write_file":
            path = args.get("path", "")
            content = args.get("content", "")
            full_path = os.path.join("/work", path.lstrip("/"))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"tool": "write_file", "ok": True, "answer": f"Geschrieben: {path}", "args": args}
        
        elif tool == "list_dir":
            path = args.get("path", ".")
            full_path = os.path.join("/work", path.lstrip("/")) if path != "/" else "/"
            files = os.listdir(full_path)
            return {"tool": "list_dir", "ok": True, "answer": "\n".join(files), "args": args}
        
        elif tool == "run_python":
            code = args.get("code", "")
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=30, cwd="/work"
            )
            return {
                "tool": "run_python", 
                "ok": proc.returncode == 0, 
                "answer": proc.stdout + proc.stderr, 
                "args": args,
                "exit_code": proc.returncode
            }
        
        elif tool == "fetch_url":
            # Im Sandbox nur über Proxy möglich - hier vereinfacht
            return {"tool": "fetch_url", "ok": False, "answer": "Nicht implementiert in Demo-Agent", "args": args, "blocked": True}
        
        elif tool == "finish":
            return {"tool": "finish", "ok": True, "answer": args.get("answer", ""), "args": args}
        
        else:
            return {"tool": tool, "ok": False, "answer": f"Unbekanntes Werkzeug: {tool}", "args": args, "blocked": True}
    
    except Exception as e:
        return {"tool": tool, "ok": False, "answer": f"Fehler: {e}", "args": args, "blocked": True}


def collect_files() -> List[Dict[str, Any]]:
    """Sammelt Dateien aus /work für den Bericht."""
    files = []
    for root, dirs, filenames in os.walk("/work"):
        for name in sorted(filenames):
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as f:
                    content = f.read(64 * 1024)
                files.append({
                    "pfad": path,
                    "bytes": len(content),
                    "inhalt": content.decode("utf-8", "replace"),
                })
            except OSError as e:
                files.append({"pfad": path, "bytes": 0, "inhalt": f"(nicht lesbar: {e})"})
    return files


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BrokenPipeError:
        sys.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)