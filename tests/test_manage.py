import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('manage', Path(__file__).resolve().parents[1] / 'scripts/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class ConfigurationTests(unittest.TestCase):
    def test_reject_domain_config_injection(self):
        for value in ('https://ai.example.com', 'example.com\nimport evil', '*.example.com', 'a..com', 'x.com {'):
            with self.assertRaises(ValueError):
                manage.validate_domain(value)

    def test_model_host_must_be_private_tailnet_address(self):
        for value in ('127.0.0.1', '8.8.8.8', 'example.com'):
            with self.assertRaises(ValueError):
                manage.validate_model_host(value)

    def test_config_preserves_secret_and_literal_password(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = root / '.env'
            args = types.SimpleNamespace(domain='ai.example.com', model_host='100.64.0.1')
            password = 'Literal-$-quotes-\"-=-password'
            with patch.object(manage, 'ROOT', root), patch.object(manage, 'ENV', env), patch('builtins.input', return_value='admin@example.com'), patch('getpass.getpass', return_value=password), contextlib.redirect_stdout(io.StringIO()):
                manage.configure(args)
                first = manage.read_config()
                with patch('getpass.getpass', side_effect=AssertionError('must not reset password')):
                    manage.configure(args)
                second = manage.read_config()
            self.assertEqual(first['WEBUI_SECRET_KEY'], second['WEBUI_SECRET_KEY'])
            self.assertEqual(password, second['WEBUI_ADMIN_PASSWORD'])
            self.assertEqual(0o600, env.stat().st_mode & 0o777)

    def test_compose_disables_implicit_dotenv_interpolation(self):
        with patch.object(manage, 'run') as run:
            manage.compose('config', '--quiet')
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ['sudo', 'docker', 'compose', '--env-file', '/dev/null'])


class PublishTests(unittest.TestCase):
    def test_existing_individual_import_gets_only_exact_new_site(self):
        caddy = Path('/etc/caddy/Caddyfile')
        site = Path('/etc/caddy/sites/core-ai.caddy')
        original = 'import /etc/caddy/sites/other.caddy\n'
        candidate = manage.site_import_config(original, caddy, site)
        self.assertIn(original.strip(), candidate)
        self.assertIn('import /etc/caddy/sites/core-ai.caddy\n', candidate)
        self.assertNotIn('*.caddy', candidate)
        self.assertEqual(candidate, manage.site_import_config(candidate, caddy, site))

    def test_existing_wildcard_is_preserved(self):
        for original in ('import /etc/caddy/sites/*.caddy\n', 'import "sites/*.caddy" # existing\n', 'import\t/etc/caddy/sites/*\n'):
            with self.subTest(original=original):
                self.assertEqual(original, manage.site_import_config(original, Path('/etc/caddy/Caddyfile'), Path('/etc/caddy/sites/core-ai.caddy')))

    @unittest.skipUnless(shutil.which('caddy'), 'Caddy CLI is required for integration validation')
    def test_actual_caddy_accepts_existing_individual_site_plus_new_site(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sites = root / 'sites'
            sites.mkdir()
            other = sites / 'other.caddy'
            other.write_text('http://other.example.test {\n respond "existing"\n}\n')
            site = sites / 'core-ai.caddy'
            site.write_text('http://ai.example.test {\n reverse_proxy 127.0.0.1:3100\n}\n')
            caddy = root / 'Caddyfile'
            original = f'import {other}\n'
            # Reproduce the previous bug with a duplicate wildcard import.
            caddy.write_text(original + f'import {sites}/*.caddy\n')
            bad = subprocess.run(['caddy', 'adapt', '--config', str(caddy), '--adapter', 'caddyfile'], capture_output=True, text=True)
            self.assertNotEqual(0, bad.returncode)
            self.assertIn('ambiguous site definition', bad.stderr)
            caddy.write_text(manage.site_import_config(original, caddy, site))
            fixed = subprocess.run(['caddy', 'adapt', '--config', str(caddy), '--adapter', 'caddyfile'], capture_output=True, text=True)
            self.assertEqual(0, fixed.returncode, fixed.stderr)

    def test_caddy_validation_failure_restores_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            caddy = root / 'Caddyfile'
            site = root / 'sites/core-ai.caddy'
            backups = root / 'backups'
            original = ':80 {\n respond "existing"\n}\n'
            caddy.write_text(original)

            def fake_run(command, **kwargs):
                command = [str(x) for x in command]
                if command[:2] == ['sudo', 'cat']:
                    return subprocess.CompletedProcess(command, 0, Path(command[2]).read_text(), '')
                if command[:3] == ['sudo', 'caddy', 'adapt']:
                    return subprocess.CompletedProcess(command, 0, '{}', '')
                if command[:3] == ['sudo', 'caddy', 'validate']:
                    raise subprocess.CalledProcessError(1, command)
                if command[:3] == ['sudo', 'mkdir', '-p']:
                    for p in command[3:]: Path(p).mkdir(parents=True, exist_ok=True)
                elif command[:3] == ['sudo', 'cp', '-a']:
                    shutil.copy2(command[3], command[4])
                elif command[:2] == ['sudo', 'install']:
                    shutil.copyfile(command[-2], command[-1])
                elif command[:3] == ['sudo', 'rm', '-f']:
                    Path(command[3]).unlink(missing_ok=True)
                return subprocess.CompletedProcess(command, 0, '', '')

            def fake_subprocess(command, **kwargs):
                if command[:3] == ['sudo', 'test', '-e']:
                    return subprocess.CompletedProcess(command, 0 if Path(command[-1]).exists() else 1)
                return subprocess.CompletedProcess(command, 0)

            with patch.object(manage, 'CADDYFILE', caddy), patch.object(manage, 'CADDYSITE', site), patch.object(manage, 'CADDYBACKUPS', backups), patch.object(manage, 'read_config', return_value={'WEBUI_URL':'https://ai.example.com'}), patch.object(manage, 'wait_ready'), patch.object(manage, 'verify_admin'), patch.object(manage, 'run', side_effect=fake_run), patch('subprocess.run', side_effect=fake_subprocess):
                with self.assertRaises(subprocess.CalledProcessError):
                    manage.publish()
            self.assertEqual(original, caddy.read_text())
            self.assertFalse(site.exists())


if __name__ == '__main__':
    unittest.main()
