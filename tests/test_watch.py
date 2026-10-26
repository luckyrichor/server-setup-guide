import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('watch', Path(__file__).parents[1]/'scripts/claude_webshare_watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
REAL_DIAGNOSE = watch.diagnose


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.gate = patch.object(watch, 'set_gate')
        self.gate_mock = self.gate.start()
        self.addCleanup(self.gate.stop)
        self.diag = patch.object(watch, 'diagnose', return_value={'summary':'isolated test diagnostic'})
        self.diag_mock = self.diag.start()
        self.addCleanup(self.diag.stop)

    def test_routes(self):
        proxies = {'ws': {'type': 'Socks5'}, 'airport': {'type': 'Selector', 'now':'node'},
                   'node': {'type':'Trojan'}, 'GLOBAL': {'type':'Selector','now':'ws'}}
        rules = [{'type':'AND','payload':'((Network,tcp) && (DomainSuffix,ifconfig.me))','proxy':'ws'}]
        self.assertTrue(watch.route_uses_webshare('rule',proxies,rules,{'ws'},'ifconfig.me'))
        self.assertFalse(watch.route_uses_webshare('rule',proxies,[{'type':'Match','proxy':'airport'}],{'ws'},'ifconfig.me'))
        self.assertFalse(watch.route_uses_webshare('direct',proxies,rules,{'ws'},'ifconfig.me'))
        self.assertTrue(watch.route_uses_webshare('global',proxies,rules,{'ws'},'ifconfig.me'))

    def test_continuous_kill_until_recovery_and_no_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings={'state_path':str(Path(tmp)/'state.json')}
            with patch.object(watch,'check',return_value=(False,'test failure')), \
                 patch.object(watch,'snapshot',return_value=[]) as snap, \
                 patch.object(watch,'kill_snapshot',return_value=([],[])) as kill, \
                 patch.object(watch,'notify',return_value=True):
                watch.run(settings)
                watch.run(settings)
                self.assertEqual(kill.call_count,2)
                with patch.object(watch,'check',return_value=(True,'recovered')):
                    watch.run(settings)
                self.assertEqual(kill.call_count,2)
                watch.run(settings)
                self.assertEqual(kill.call_count,3)
                self.assertEqual(snap.call_count,3)
                self.assertEqual([c.args[1] for c in self.gate_mock.call_args_list], [True,True,False,True])

    def test_failed_alert_retried_even_after_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings={'state_path':str(Path(tmp)/'state.json')}
            with patch.object(watch,'check',return_value=(False,'failure')), \
                 patch.object(watch,'snapshot',return_value=[]), \
                 patch.object(watch,'kill_snapshot',return_value=([],[])) as kill, \
                 patch.object(watch,'notify',side_effect=[False,True]) as send:
                watch.run(settings)
                with patch.object(watch,'check',return_value=(True,'ok')):
                    watch.run(settings)
                self.assertEqual(kill.call_count,1)
                self.assertEqual(send.call_count,2)

    def test_recovery_notifies_once_and_retries_without_killing(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            settings={'state_path':str(Path(tmp)/'state.json')}
            with patch.object(watch,'check',return_value=(True,'ok')), \
                 patch.object(watch,'snapshot',return_value=[]), \
                 patch.object(watch,'kill_snapshot',return_value=([],[])) as kill, \
                 patch.object(watch,'notify',side_effect=[True,False,True]) as send:
                watch.run(settings)  # Initial health is not a recovery.
                send.assert_not_called()
                with patch.object(watch,'check',return_value=(False,'failure')):
                    watch.run(settings)
                watch.run(settings)  # Recovery delivery fails, remains queued.
                self.assertEqual(len(json.loads(Path(settings['state_path']).read_text())['pending_alerts']),1)
                watch.run(settings)  # Retry succeeds with same idempotency key.
                watch.run(settings)  # Continued health produces no duplicate.
                self.assertEqual(send.call_count,3)
                self.assertEqual(send.call_args_list[1].args[2],send.call_args_list[2].args[2])
                self.assertIn('已恢复',send.call_args_list[1].args[1])
                self.assertEqual(kill.call_count,1)

    def test_gate_failure_keeps_claude_blocked_and_stopped(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            settings={'state_path':str(Path(tmp)/'state.json')}
            with patch.object(watch,'check',return_value=(True,'ok')), \
                 patch.object(watch,'set_gate',side_effect=RuntimeError('gate failure')), \
                 patch.object(watch,'snapshot',return_value=[]), \
                 patch.object(watch,'kill_snapshot',return_value=([],[])) as kill, \
                 patch.object(watch,'notify',return_value=True):
                watch.run(settings)
                self.assertFalse(json.loads(Path(settings['state_path']).read_text())['healthy'])
                kill.assert_called_once()

    def test_probe_only_never_changes_gate(self):
        with patch.object(watch,'check',return_value=(False,'failed')):
            self.assertEqual(watch.run({},probe_only=True),1)
            self.gate_mock.assert_not_called()

    def test_diagnosis_happens_after_stop_and_persist(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            settings={'state_path':str(Path(tmp)/'state.json')}
            with patch.object(watch,'check',return_value=(False,'failure')), \
                 patch.object(watch,'snapshot',return_value=[]), \
                 patch.object(watch,'kill_snapshot',return_value=([],[])) as kill, \
                 patch.object(watch,'notify',return_value=True) as send:
                def diagnosis(settings):
                    kill.assert_called_once()
                    self.assertTrue(self.gate_mock.call_args.args[1])
                    self.assertFalse(json.loads(Path(settings['state_path']).read_text())['healthy'])
                    return {'summary':'verified staged result'}
                self.diag_mock.side_effect=diagnosis
                watch.run(settings)
                self.assertIn('verified staged result',send.call_args.args[1])
                self.assertIn('diagnostics',json.loads(Path(settings['state_path']).read_text()))

    def test_diagnostic_summary_does_not_overclaim(self):
        text=watch.summarize_diagnostics({'ok':False},[
            {'ok':False,'host':'ifconfig.me','stage':'webshare_socks','error_type':'TimeoutError'},
            {'ok':True,'host':'api.ipify.org','stage':'complete'}])
        self.assertIn('不能仅凭此确定',text)
        self.assertIn('SOCKS握手未完成',text)
        text=watch.summarize_diagnostics({'ok':True},[
            {'ok':True,'host':'ifconfig.me'}, {'ok':True,'host':'api.ipify.org'}])
        self.assertIn('不能追溯确定原故障段',text)

    def test_diagnostic_timeout_is_bounded(self):
        with patch.object(watch.subprocess,'run',side_effect=subprocess.TimeoutExpired('isolated',18)) as run:
            # Bypass the setUp mock to exercise the actual wrapper.
            result=REAL_DIAGNOSE({})
            self.assertIn('超时',result['summary'])
            self.assertEqual(run.call_args.kwargs['timeout'],18)

    def test_trace_stages_and_no_secret_output(self):
        import json
        from unittest.mock import MagicMock
        settings={'proxy_url':'http://127.0.0.1:7890','expected_ip':'192.0.2.10'}
        node={'name':'ws','server':'192.0.2.10','port':1080,'dialer-proxy':'airport',
              'username':'private-test-user','password':'private-test-password'}
        proxies={'airport':{'type':'Selector','now':'first'}}
        prefix=b'HTTP/1.1 200 Connection established\r\n\r\n'
        cases=[('socks_timeout',b'', 'webshare_socks'),
               ('auth_rejected',b'\x05\x02\x01\x01','webshare_auth'),
               ('target_rejected',b'\x05\x02\x01\x00\x05\x04\x00\x01','webshare_to_target'),
               ('tls_failure',b'\x05\x02\x01\x00\x05\x00\x00\x01'+b'\0'*6,'target_tls'),
               ('http_failure',b'\x05\x02\x01\x00\x05\x00\x00\x01'+b'\0'*6,'target_http'),
               ('success',b'\x05\x02\x01\x00\x05\x00\x00\x01'+b'\0'*6,'complete')]
        for label,body,expected in cases:
            with self.subTest(label=label):
                stream=MagicMock();stream.getsockname.return_value=('127.0.0.1',4567)
                data=bytearray(prefix+body)
                def recv(n):
                    if not data:raise TimeoutError('not exported')
                    out=bytes(data[:n]);del data[:n];return out
                stream.recv.side_effect=recv
                context=MagicMock();context.wrap_socket.return_value=stream
                if label=='tls_failure':context.wrap_socket.side_effect=watch.ssl.SSLError('not exported')
                response=MagicMock();response.status=403 if label=='http_failure' else 200
                response.read.return_value=b'192.0.2.10'
                route={'connections':[{'metadata':{'sourcePort':'4567'},'chains':['first','airport']}]}
                with patch.object(watch.socket,'create_connection',return_value=stream), \
                     patch.object(watch,'diagnostic_api',return_value=route), \
                     patch.object(watch.ssl,'create_default_context',return_value=context), \
                     patch.object(watch.http.client,'HTTPResponse',return_value=response):
                    result=watch.trace_webshare(settings,{},proxies,node,'ifconfig.me')
                self.assertEqual(result['stage'],expected)
                self.assertEqual(result['ok'],label=='success')
                self.assertNotIn(node['username'],json.dumps(result))
                self.assertNotIn(node['password'],json.dumps(result))

    def test_trace_refuses_unconfirmed_route_and_skips_first_in_direct_mode(self):
        from unittest.mock import MagicMock
        settings={'proxy_url':'http://127.0.0.1:7890','expected_ip':'192.0.2.10'}
        node={'name':'ws','server':'192.0.2.10','port':1080,'dialer-proxy':'DIRECT'}
        self.assertIsNone(watch.trace_webshare(settings,{}, {},node,'ifconfig.me')['ok'])
        node['dialer-proxy']='airport'
        stream=MagicMock();stream.getsockname.return_value=('127.0.0.1',4567)
        data=bytearray(b'HTTP/1.1 200 Connection established\r\n\r\n')
        def recv(n):
            out=bytes(data[:n]);del data[:n];return out
        stream.recv.side_effect=recv
        with patch.object(watch.socket,'create_connection',return_value=stream), \
             patch.object(watch,'diagnostic_api',return_value={'connections':[{'metadata':{'sourcePort':4567},'chains':['DIRECT']}] }):
            result=watch.trace_webshare(settings,{}, {'airport':{'type':'Selector','now':'first'}},node,'ifconfig.me')
        self.assertIsNone(result['ok'])
        self.assertEqual(result['stage'],'route_confirmation')
        self.assertEqual(stream.sendall.call_count,1)  # No authentication sent.

    def test_real_pidfd_only_sacrificial_process(self):
        child=subprocess.Popen(['sleep','60'])
        try:
            info=watch.process_info(child.pid)
            killed,failed=watch.kill_snapshot([info])
            self.assertEqual(killed,[child.pid])
            self.assertEqual(failed,[])
            self.assertEqual(child.wait(timeout=3),-9)
        finally:
            if child.poll() is None:child.kill();child.wait()

    def test_pid_reuse_guard(self):
        child=subprocess.Popen(['sleep','60'])
        try:
            info=watch.process_info(child.pid);info['start']='wrong identity'
            self.assertEqual(watch.kill_snapshot([info]),([],[]))
            self.assertIsNone(child.poll())
        finally:
            child.kill();child.wait()


if __name__=='__main__':unittest.main()
