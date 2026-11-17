import base64
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import network

KEY = base64.b64encode(bytes(range(32))).decode()
OTHER = base64.b64encode(bytes(range(32, 64))).decode()


class NetworkTests(unittest.TestCase):
    def test_config_routes_only_the_model_peer(self):
        config = network.render(KEY, OTHER)
        self.assertIn('AllowedIPs = 10.203.0.2/32', config)
        self.assertNotIn('0.0.0.0/0', config)
        self.assertNotIn('DNS', config)

    def test_reject_key_injection_and_noncanonical_keys(self):
        for value in (KEY + '\nPostUp = evil', 'AAAA', 'hello', ''):
            with self.assertRaises(ValueError):
                network.validate_key(value)

    def test_endpoint_rejects_shell_and_config_injection(self):
        for value in ('x;whoami', 'https://example.com', '-oProxyCommand=evil', 'x\nAllowedIPs=0.0.0.0/0', 'example.com:22', '127.0.0.1'):
            with self.assertRaises(ValueError):
                network.validate_endpoint(value)

    def test_public_export_contains_no_private_key_material(self):
        info = network.public_info(OTHER, 'vps.example.test')
        self.assertEqual({'server_public_key','endpoint','port','server_ip','client_ip'}, set(info))
        self.assertEqual(OTHER, info['server_public_key'])
        self.assertNotIn(KEY, str(info))

    def test_enrollment_preserves_a_different_existing_peer(self):
        from subprocess import CompletedProcess
        with patch.object(network, 'read_existing', return_value=network.render(KEY, OTHER)), patch.object(network, 'run', return_value=CompletedProcess([],0,KEY+'\n')), patch.object(network, 'apply') as apply:
            third = base64.b64encode(bytes([9]*32)).decode()
            with self.assertRaisesRegex(ValueError, 'different laptop'):
                network.add_peer({'CORE_VPS_ENDPOINT':'vps.example.test'}, third)
            apply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
