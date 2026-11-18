from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'Caddyfile'
    text=(root/'deploy/workstation.Caddyfile').read_text().replace('DOMAIN','ai.example.invalid',1)
    path.write_text(text)
    subprocess.run(['caddy','adapt','--config',str(path),'--adapter','caddyfile','--validate'],check=True,stdout=subprocess.DEVNULL)
print('CORE-AI Caddy template valid')
