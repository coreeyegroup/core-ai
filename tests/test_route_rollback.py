from pathlib import Path
import importlib.util
from unittest.mock import patch
import pytest

spec=importlib.util.spec_from_file_location('deploy_route',Path(__file__).resolve().parents[1]/'scripts/deploy-workstation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_caddy_validation_failure_restores_exact_configuration(tmp_path):
    root=tmp_path/'source';(root/'deploy').mkdir(parents=True)
    (root/'deploy/workstation.Caddyfile').write_text('DOMAIN {\n reverse_proxy 127.0.0.1:18787\n}\n')
    caddy=tmp_path/'Caddyfile';caddy.write_text('import other.caddy\n')
    site=tmp_path/'sites/core-ai.caddy';site.parent.mkdir();old='# Managed by CORE-AI previous\nai.example.com {\n reverse_proxy 127.0.0.1:3101\n}\n';site.write_text(old)
    def fail(*args,**kwargs):raise RuntimeError('validation failed')
    with patch.object(module,'CADDY',caddy),patch.object(module,'SITE',site),patch.object(module,'run',side_effect=fail),patch.object(module.subprocess,'run'):
        with pytest.raises(RuntimeError):module.install_route(root,'ai.example.com')
    assert caddy.read_text()=='import other.caddy\n'
    assert site.read_text()==old

def test_refuse_unmanaged_route_before_write(tmp_path):
    caddy=tmp_path/'Caddyfile';caddy.write_text('original\n')
    site=tmp_path/'core-ai.caddy';site.write_text('unmanaged\n')
    with patch.object(module,'CADDY',caddy),patch.object(module,'SITE',site):
        with pytest.raises(ValueError):module.install_route(tmp_path,'ai.example.com')
    assert site.read_text()=='unmanaged\n' and caddy.read_text()=='original\n'
