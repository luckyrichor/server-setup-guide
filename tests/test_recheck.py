import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

spec = importlib.util.spec_from_file_location('watch_recheck', Path(__file__).parents[1] / 'scripts/claude_webshare_watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = Path(self.tmp.name) / 'config.yaml'
        config.write_text(yaml.safe_dump({'secret': 'test-only', 'proxies': [
            {'name': 'ws', 'type': 'socks5', 'server': '192.0.2.10'}]}))
        self.settings = {'mihomo_config': str(config), 'controller': 'http://127.0.0.1:19090',
            'webshare_server': '192.0.2.10', 'expected_ip': '192.0.2.20',
            'proxy_url': 'http://127.0.0.1:7890', 'probe_host': 'ifconfig.me',
            'probe_url': 'https://ifconfig.me/ip', 'fallback_probe_url': 'https://ipinfo.io/ip'}
        self.rules = [{'type': 'Network', 'payload': 'tcp', 'proxy': 'ws'}]
        self.rules_reads = 0
        self.change_after = False

        def open_api(request, timeout):
            path = request.full_url.rsplit('/', 1)[-1]
            if path == 'configs':
                data = {'mode': 'rule'}
            elif path == 'proxies':
                data = {'proxies': {'ws': {'type': 'Socks5'}}}
            elif path == 'rules':
                self.rules_reads += 1
                data = {'rules': ([{'type': 'Match', 'proxy': 'DIRECT'}]
                    if self.change_after and self.rules_reads > 1 else self.rules)}
            else:
                raise AssertionError(path)
            return io.BytesIO(json.dumps(data).encode())

        opener = MagicMock()
        opener.open.side_effect = open_api
        patcher = patch.object(watch.urllib.request, 'build_opener', return_value=opener)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_probe(self, replies):
        with patch.object(watch.subprocess, 'run', side_effect=replies) as run:
            result = watch.check(self.settings)
        return result, run.call_args_list

    def reply(self, code=0, body='192.0.2.20'):
        return subprocess.CompletedProcess([], code, body, 'test transport failure')

    def test_transient_tls_failure_uses_independent_verified_exit(self):
        result, calls = self.run_probe([self.reply(35, ''), self.reply()])
        self.assertTrue(result[0])
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0].args[0][-1], calls[1].args[0][-1])

    def test_timeout_uses_one_independent_recheck(self):
        result, calls = self.run_probe([self.reply(28, ''), self.reply()])
        self.assertTrue(result[0])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[0][-1], 'https://ipinfo.io/ip')

    def test_second_failure_remains_unhealthy_without_unbounded_retry(self):
        result, calls = self.run_probe([self.reply(35, ''), self.reply(56, '')])
        self.assertFalse(result[0])
        self.assertEqual(len(calls), 2)

    def test_wrong_fallback_exit_cannot_release_gate(self):
        result, calls = self.run_probe([self.reply(56, ''), self.reply(body='192.0.2.99')])
        self.assertFalse(result[0])
        self.assertEqual(len(calls), 2)

    def test_wrong_primary_exit_is_not_retried(self):
        result, calls = self.run_probe([self.reply(body='192.0.2.99')])
        self.assertFalse(result[0])
        self.assertEqual(len(calls), 1)

    def test_http_failure_is_not_masked_by_another_site(self):
        result, calls = self.run_probe([self.reply(22, '')])
        self.assertFalse(result[0])
        self.assertEqual(len(calls), 1)

    def test_fallback_without_webshare_route_is_never_requested(self):
        self.rules = [{'type': 'Domain', 'payload': 'ifconfig.me', 'proxy': 'ws'},
            {'type': 'Match', 'proxy': 'DIRECT'}]
        result, calls = self.run_probe([self.reply(35, '')])
        self.assertFalse(result[0])
        self.assertEqual(len(calls), 1)

    def test_route_change_after_fallback_prevents_success(self):
        self.change_after = True
        result, calls = self.run_probe([self.reply(35, ''), self.reply()])
        self.assertFalse(result[0])


class DirectTraceTests(unittest.TestCase):
    def node(self):
        return {'name': 'ws', 'server': '192.0.2.10', 'port': 80, 'dialer-proxy': 'DIRECT',
            'username': 'test-user', 'password': 'private-test-password'}

    def test_bound_direct_connection_reports_tls_failure_without_secret_output(self):
        stream = MagicMock()
        stream.getsockopt.return_value = b'eth0\0'
        data = bytearray(b'\x05\x02\x01\x00\x05\x00\x00\x01' + b'\0' * 6)

        def recv(n):
            out = bytes(data[:n])
            del data[:n]
            return out

        stream.recv.side_effect = recv
        context = MagicMock()
        context.wrap_socket.side_effect = watch.ssl.SSLError('private-test-password')
        with patch.object(watch.socket, 'socket', return_value=stream), \
             patch.object(watch.socket, 'if_nametoindex', return_value=2), \
             patch.object(watch.ssl, 'create_default_context', return_value=context):
            result = watch.trace_webshare({'direct_interface': 'eth0', 'expected_ip': '192.0.2.20'},
                {'tun': {'device': 'test-tun'}}, {}, self.node(), 'ifconfig.me')
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'target_tls')
        self.assertNotIn('private-test-password', json.dumps(result))

    def test_binding_failure_never_transmits_credentials(self):
        stream = MagicMock()
        stream.setsockopt.side_effect = PermissionError('cannot bind')
        with patch.object(watch.socket, 'socket', return_value=stream), \
             patch.object(watch.socket, 'if_nametoindex', return_value=2):
            result = watch.trace_webshare({'direct_interface': 'eth0'}, {}, {}, self.node(), 'ifconfig.me')
        self.assertFalse(result['ok'])
        stream.sendall.assert_not_called()


if __name__ == '__main__':
    unittest.main()
