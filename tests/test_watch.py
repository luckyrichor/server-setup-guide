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
    def test_routes(self):
        proxies = {'ws': {'type': 'Socks5'}, 'airport': {'type': 'Selector', 'now':'node'},
                   'node': {'type':'Trojan'}, 'GLOBAL': {'type':'Selector','now':'ws'}}
        rules = [{'type':'AND','payload':'((Network,tcp) && (DomainSuffix,ifconfig.me))','proxy':'ws'}]
        self.assertTrue(watch.route_uses_webshare('rule',proxies,rules,{'ws'},'ifconfig.me'))
        self.assertFalse(watch.route_uses_webshare('rule',proxies,[{'type':'Match','proxy':'airport'}],{'ws'},'ifconfig.me'))
        self.assertFalse(watch.route_uses_webshare('direct',proxies,rules,{'ws'},'ifconfig.me'))
        self.assertTrue(watch.route_uses_webshare('global',proxies,rules,{'ws'},'ifconfig.me'))

    def test_one_kill_per_incident_and_no_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings={'state_path':str(Path(tmp)/'state.json')}
            with patch.object(watch,'check',return_value=(False,'test failure')), \
                 patch.object(watch,'snapshot',return_value=[]) as snap, \
                 patch.object(watch,'kill_snapshot',return_value=([],[])) as kill, \
                 patch.object(watch,'notify',return_value=True):
                watch.run(settings)
                watch.run(settings)
                self.assertEqual(kill.call_count,1)
                with patch.object(watch,'check',return_value=(True,'recovered')):
                    watch.run(settings)
                self.assertEqual(kill.call_count,1)
                watch.run(settings)
                self.assertEqual(kill.call_count,2)
                self.assertEqual(snap.call_count,2)

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
