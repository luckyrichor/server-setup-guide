import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('watch_delay', Path(__file__).parents[1]/'scripts/claude_webshare_watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class AlertDelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = {'state_path': str(Path(self.tmp.name)/'state.json')}
        self.clock = 1000
        for name, value in [('set_gate', None), ('snapshot', []), ('kill_snapshot', ([], [])),
                            ('notify', True), ('diagnose', {'summary': 'isolated'})]:
            mock = patch.object(watch, name, return_value=value)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)

    def tick(self, second, healthy):
        with patch.object(watch.time, 'time', return_value=1000+second), \
             patch.object(watch, 'check', return_value=(healthy, 'ok' if healthy else 'failed')), \
             contextlib.redirect_stdout(io.StringIO()):
            watch.run(self.settings)
        return json.loads(Path(self.settings['state_path']).read_text())

    def test_short_fault_blocks_immediately_but_never_notifies(self):
        self.assertFalse(self.tick(0, False)['healthy'])
        self.kill_snapshot.assert_called_once()
        self.assertFalse(self.tick(30, True)['healthy'])
        self.assertTrue(self.tick(60, True)['healthy'])
        self.assertEqual([c.args[1] for c in self.set_gate.call_args_list], [True, True, False])
        self.assertEqual(self.kill_snapshot.call_count, 2)
        self.notify.assert_not_called()
        self.diagnose.assert_not_called()

    def test_persistent_fault_announces_once_at_ninety_seconds(self):
        for second in (0, 30, 89): self.tick(second, False)
        self.notify.assert_not_called()
        self.tick(90, False)
        self.notify.assert_called_once()
        self.tick(120, False)
        self.notify.assert_called_once()
        self.assertFalse(self.tick(150, True)['healthy'])
        self.assertTrue(self.tick(180, True)['healthy'])
        self.assertEqual(self.notify.call_count, 2)
        self.assertIn('已恢复', self.notify.call_args.args[1])
        self.tick(210, True)
        self.assertEqual(self.notify.call_count, 2)

    def test_failure_resets_recovery_streak(self):
        self.tick(0, False)
        self.tick(30, True)
        self.tick(60, False)
        self.assertFalse(self.tick(90, True)['healthy'])
        self.assertTrue(self.tick(120, True)['healthy'])
        self.notify.assert_not_called()

    def test_first_healthy_sample_at_delay_does_not_send_failure(self):
        self.tick(0, False)
        self.assertFalse(self.tick(90, True)['healthy'])
        self.assertTrue(self.tick(120, True)['healthy'])
        self.notify.assert_not_called()

    def test_second_incident_has_fresh_delay_and_id(self):
        first = self.tick(0, False)['incident_id']
        self.tick(30, True); self.tick(60, True)
        with patch.object(watch.time, 'time_ns', return_value=123):
            state = self.tick(120, False)
        self.assertNotEqual(first, state['incident_id'])
        self.assertEqual(state['failure_started_at'], 1120)
        self.tick(150, False)
        self.notify.assert_not_called()

    def test_failed_delivery_preserves_order_and_idempotency(self):
        self.tick(0, False)
        self.notify.return_value = False
        self.tick(90, False)
        failed_id = self.notify.call_args.args[2]
        self.tick(120, True)
        self.assertFalse(self.tick(150, True)['pending_alerts'] == [])
        self.notify.return_value = True
        self.tick(180, True)
        self.assertEqual(self.notify.call_args.args[2], failed_id)
        self.tick(210, True)
        self.assertEqual(self.notify.call_args.args[2], failed_id+'-recovered')

    def test_gate_failure_cannot_release_after_success(self):
        self.tick(0, False); self.tick(30, True)
        self.set_gate.side_effect = RuntimeError('test-only')
        state = self.tick(60, True)
        self.assertFalse(state['healthy'])
        self.assertEqual(state['recovery_successes'], 0)
        self.assertTrue(state['gate_error'])

    def test_legacy_incident_still_receives_one_recovery(self):
        Path(self.settings['state_path']).write_text(json.dumps({
            'incident': True, 'healthy': False, 'incident_id': 'legacy', 'checked_at': 999}))
        self.tick(0, True)
        self.assertTrue(self.tick(30, True)['healthy'])
        self.assertEqual(self.notify.call_args.args[2], 'legacy-recovered')

    def test_initial_health_has_no_recovery_notification(self):
        self.assertTrue(self.tick(0, True)['healthy'])
        self.notify.assert_not_called()
