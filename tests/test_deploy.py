import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('deploy',Path(__file__).resolve().parents[1]/'scripts/deploy-workstation.py')
deploy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

class DeploymentTests(unittest.TestCase):
    def test_exact_import_preserves_other_sites(self):
        caddy=Path('/etc/caddy/Caddyfile');site=Path('/etc/caddy/sites/core-ai.caddy')
        old='import /etc/caddy/sites/another.caddy\n'
        new=deploy.site_import(old,caddy,site)
        self.assertIn('import /etc/caddy/sites/core-ai.caddy',new)
        self.assertNotIn('sites/*.caddy',new)
        self.assertTrue(new.startswith(old))
    def test_existing_glob_not_duplicated(self):
        old='import /etc/caddy/sites/*.caddy\n'
        self.assertEqual(deploy.site_import(old),old)
    def test_domain_validation(self):
        for value in ['https://host.example','bad\nimport evil','../path','localhost','UPPER.example']:
            with self.assertRaises(ValueError):deploy.domain(value)
    def test_services_are_product_scoped(self):
        unit=deploy.service_text(Path('/opt/core-ai/releases/test'),True)
        self.assertIn('User=core-ai',unit)
        self.assertIn('core_ai.worker',unit)
        self.assertIn('ProtectHome=true',unit)
        self.assertNotIn('corei-os-mini',unit)
        self.assertNotIn('docker.sock',unit)
