import os
# Si el archivo ya tiene import os, no pasa nada; si no, lo añade
if not any('import os' in line for line in open('modules/llm_client.py')):
    with open('modules/llm_client.py', 'r') as f:
        content = f.read()
    with open('modules/llm_client.py', 'w') as f:
        f.write('import os\n' + content)
# Reemplazar localhost por ollama
import subprocess
subprocess.run(["sed", "-i", "s/localhost:11434/ollama:11434/g", "modules/llm_client.py"])
