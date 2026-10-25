import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('watch', Path(__file__).parents[1]/'scripts/claude_webshare_watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.gate = patch.object(watch, 'set_gate')
        self.gate_mock = self.gate.start()
        self.addCleanup(self.gate.stop)

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
