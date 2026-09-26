import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cmd_cmd.pool import NoRedirect, PolicyError, candidates, discover, model_ids, route

NOW = 1000
LOW = 'gemini-3.8-flash-low'
HIGH = 'gemini-3.8-flash-high'
MEDIUM = 'gemini-3.8-flash-medium'
PRO = 'gemini-3.1-pro-high'
CLAUDE = 'claude-sonnet-4-6'
DEEP = 'deepseek-v4-flash-fast'


def profile(difficulty=2, escalation=False, cost=1):
    return {'roles': ['controller', 'planner', 'worker', 'verifier'],
            'capabilities': ['tools'], 'max_difficulty': difficulty,
            'escalation_only': escalation, 'context_window': 32000,
            'max_output': 4000, 'cost': {'input': cost, 'output': cost}}


def fixture():
    policy = json.loads(Path('config/routing.example.json').read_text())
    agy = {m: profile(3 if m in (PRO, CLAUDE) else 2, m in (PRO, CLAUDE))
           for m in (LOW, HIGH, MEDIUM, PRO, CLAUDE)}
    policy['providers']['agy']['models'] = agy
    policy['providers']['goat'].update(enabled=True, models={DEEP: profile(cost=0.1)})
    snapshots = [{'provider': provider, 'observed_at': NOW, 'data': [{'id': m} for m in models]}
                 for provider, models in [('agy', agy), ('goat', [DEEP])]]
    native = {'observed_at': NOW, 'data': [{'id': 'agy/' + m} for m in agy] + [{'id': DEEP}]}
    request = {'role': 'controller', 'difficulty': 1, 'input_tokens': 1000,
               'output_tokens': 1000, 'max_cost_usd': 0.01}
    return policy, snapshots, request, native


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.snapshots, self.request, self.native = fixture()

    def choose(self, **request):
        self.request.update(request)
        return route(self.policy, self.snapshots, self.request, NOW, self.native)

    def test_default_controller_agy_even_with_cheaper_goat(self):
        self.assertEqual(self.choose()['model'], LOW)

    def test_planner_high_or_light_medium(self):
        self.assertEqual(self.choose(role='planner', difficulty=2)['model'], HIGH)
        self.assertEqual(self.choose(difficulty=1)['model'], MEDIUM)

    def test_dynamic_unknown_id_can_join_with_verified_metadata(self):
        model = 'new-vendor-fast'
        self.snapshots[0]['data'].append({'id': model})
        self.native['data'].append({'id': 'agy/' + model})
        self.policy['providers']['agy']['models'][model] = profile(cost=0.01)
        self.assertEqual(self.choose(role='worker')['model'], model)

    def test_unknown_capabilities_are_excluded(self):
        self.policy['providers']['agy']['models'][LOW]['capabilities'] = []
        self.assertNotEqual(self.choose()['model'], LOW)

    def test_unknown_price_is_not_free(self):
        self.policy['providers']['agy']['models'][LOW]['cost']['input'] = None
        self.assertNotEqual(self.choose()['model'], LOW)

    def test_budget_can_force_goat_fallback(self):
        self.assertEqual(self.choose(max_cost_usd=0.0003)['provider'], 'goat')
        self.assertEqual(self.choose(max_cost_usd=0)['status'], 'BLOCKED')

    def test_real_zero_cost_is_valid(self):
        self.policy['providers']['agy']['models'][LOW]['cost'] = {'input': 0, 'output': 0}
        self.assertEqual(self.choose(max_cost_usd=0)['model'], LOW)

    def test_removed_or_unregistered_model_not_selected(self):
        self.snapshots[0]['data'] = [r for r in self.snapshots[0]['data'] if r['id'] != LOW]
        self.assertNotEqual(self.choose()['model'], LOW)
        self.native['data'] = []
        self.assertEqual(self.choose()['status'], 'BLOCKED')

    def test_provider_outage_and_stale_snapshot_fallback(self):
        self.assertEqual(self.choose(unavailable=['agy'])['provider'], 'goat')
        self.request.pop('unavailable')
        self.snapshots[0]['observed_at'] = 0
        self.assertEqual(self.choose()['provider'], 'goat')
        self.snapshots = self.snapshots[:1]
        self.assertEqual(self.choose()['status'], 'BLOCKED')

    def test_escalation_not_triggered_by_outage(self):
        self.snapshots[0]['data'] = [{'id': PRO}, {'id': CLAUDE}]
        self.assertEqual(self.choose()['provider'], 'goat')
        self.assertEqual(self.choose(role='planner', verified_failure=True)['model'], PRO)
        self.assertEqual(self.choose(difficulty=3, verified_failure=False)['model'], PRO)

    def test_string_verified_failure_does_not_authorize_escalation(self):
        self.snapshots[0]['data'] = [{'id': PRO}]
        self.assertEqual(self.choose(verified_failure='true')['provider'], 'goat')

    def test_manual_pin_wins_and_no_silent_fallback(self):
        self.assertEqual(self.choose(manual_native_id='agy/' + MEDIUM)['model'], MEDIUM)
        self.assertEqual(self.choose(unavailable=['agy/' + MEDIUM])['status'], 'BLOCKED')
        self.assertEqual(self.choose(manual_native_id='absent')['status'], 'BLOCKED')

    def test_manual_escalation_is_explicit_but_budget_still_applies(self):
        self.assertEqual(self.choose(manual_native_id='agy/' + CLAUDE)['model'], CLAUDE)
        self.assertEqual(self.choose(max_cost_usd=0)['status'], 'BLOCKED')

    def test_context_and_output_capacity(self):
        self.assertEqual(self.choose(output_tokens=5000)['status'], 'BLOCKED')
        self.assertEqual(self.choose(output_tokens=1000, input_tokens=32000)['status'], 'BLOCKED')

    def test_attempts_are_bounded_and_resume_does_not_revisit(self):
        first = self.choose()
        second = self.choose(attempted=[first['identity']])
        self.assertNotEqual(first['identity'], second['identity'])
        self.assertEqual(self.choose(attempted=['a', 'a', 'b'])['status'], 'BLOCKED')

    def test_invalid_numbers_fail_closed(self):
        for value in [-1, float('nan'), float('inf'), True, '1']:
            with self.subTest(value=value), self.assertRaises(PolicyError):
                self.choose(max_cost_usd=value)

    def test_native_freshness_and_membership_required(self):
        self.native['observed_at'] = NOW + 1
        self.assertEqual(self.choose()['status'], 'BLOCKED')
        self.native['observed_at'] = 0
        self.assertEqual(self.choose()['status'], 'BLOCKED')
        self.assertEqual(route(self.policy, self.snapshots, self.request, NOW)['status'], 'BLOCKED')

    def test_identity_includes_provider(self):
        self.policy['providers']['goat']['models'][LOW] = profile(cost=0.1)
        self.snapshots[1]['data'] = [{'id': LOW}]
        self.native['data'].append({'id': LOW})
        self.assertEqual(self.choose(unavailable=['agy'])['identity'], 'goat/' + LOW)

    def test_duplicate_snapshots_and_incomplete_metadata(self):
        with self.assertRaises(PolicyError):
            candidates(self.policy, self.snapshots * 2, NOW)
        self.policy['providers']['agy']['models'] = {}
        # Default profiles contain unknown costs and no verified capabilities.
        self.policy['providers']['goat']['enabled'] = False
        self.assertEqual(self.choose()['status'], 'BLOCKED')


class DiscoveryTests(unittest.TestCase):
    def test_redirects_never_forward_credentials(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.test'))

    def test_http_discovery_path_keyless_and_dedup(self):
        seen = []
        def transport(request, timeout):
            seen.append((request, timeout))
            return io.BytesIO(b'{"data":[{"id":"b"},{"id":"a"},{"id":"a"}]}')
        self.assertEqual(discover('http://localhost:1234/v1/', opener=transport), ['a', 'b'])
        self.assertEqual(seen[0][0].full_url, 'http://localhost:1234/v1/models')
        self.assertFalse(seen[0][0].has_header('Authorization'))

    def test_environment_auth_and_no_literal_key(self):
        def transport(request, timeout):
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')
            return io.BytesIO(b'{"data":[]}')
        with patch.dict(os.environ, {'TEST_AGY_KEY': 'test-secret'}):
            self.assertEqual(discover('https://example.test/v1', 'TEST_AGY_KEY', opener=transport), [])
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(PolicyError):
            discover('https://example.test/v1', 'MISSING_KEY')

    def test_invalid_payloads(self):
        for payload in [[], {}, {'data': [None]}, {'data': [{'id': ''}]},
                        {'data': [], 'has_more': True}, {'data': [], 'next_cursor': 'x'}]:
            with self.subTest(payload=payload), self.assertRaises(PolicyError):
                model_ids(payload)

    def test_unsafe_urls_and_timeout(self):
        for url in ['http://example.test/v1', 'https://user:secret@example.test/v1',
                    'file:///tmp/x', 'https://example.test/v1?key=secret']:
            with self.subTest(url=url), self.assertRaises(PolicyError):
                discover(url)
        with self.assertRaises(PolicyError):
            discover('https://example.test/v1', timeout=31)

    def test_response_limit_and_transport_failure(self):
        with self.assertRaises(PolicyError):
            discover('http://localhost/v1', opener=lambda *a, **k: io.BytesIO(b'x' * 2_000_001))
        def failure(*args, **kwargs):
            raise TimeoutError('provider failed')
        with self.assertRaises(TimeoutError):
            discover('http://localhost/v1', opener=failure)


class CLITests(unittest.TestCase):
    def test_persistent_override_reread_and_auto_reset(self):
        policy, snapshots, request, native = fixture()
        import time
        for snap in snapshots + [native]:
            snap['observed_at'] = time.time()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in [('policy', policy), ('catalog', snapshots), ('request', request), ('native', native)]:
                (root / name).write_text(json.dumps(value))
            overrides = root / 'overrides'
            args = [sys.executable, '-m', 'cmd_cmd', 'route', '--policy', str(root/'policy'),
                    '--catalog', str(root/'catalog'), '--request', str(root/'request'),
                    '--native-catalog', str(root/'native'), '--overrides', str(overrides)]
            def run():
                result = subprocess.run(args, capture_output=True, text=True)
                return result.returncode, json.loads(result.stdout)
            self.assertEqual(run()[1]['model'], LOW)
            overrides.write_text(json.dumps({'roles': {'controller': 'agy/' + MEDIUM}}))
            self.assertEqual(run()[1]['model'], MEDIUM)
            self.assertEqual(run()[1]['model'], MEDIUM)  # saved across fresh processes
            overrides.write_text(json.dumps({'roles': {}}))
            self.assertEqual(run()[1]['model'], LOW)
            overrides.write_text(json.dumps({'roles': {'controller': 'session'}}))
            self.assertEqual(run()[1]['status'], 'MANUAL_SESSION')
            overrides.write_text('{broken')
            self.assertEqual(run()[0], 2)
            overrides.write_text(json.dumps({'roles': {}}))
            (root/'policy').write_text(json.dumps({'providers': []}))
            self.assertEqual(run()[0], 2)


if __name__ == '__main__':
    unittest.main()
