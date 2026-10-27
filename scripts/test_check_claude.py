"""Isolated behavior checks; never mutates the live Clash configuration."""
import importlib.util
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

spec = importlib.util.spec_from_file_location('checker', Path(__file__).with_name('check_claude.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
POLICY = json.loads((Path(__file__).parents[1]/'references/baseline.json').read_text())


class RuleTests(unittest.TestCase):
    def test_scoped_intercom_does_not_capture_chrome(self):
        rules = m.requirements(POLICY) + ['DOMAIN-SUFFIX,intercom.io,ChatGPT']
        self.assertEqual(m.first_target(rules, POLICY['intercom_host'], 'Claude Helper'), POLICY['fixed_proxy'])
        self.assertEqual(m.first_target(rules, POLICY['intercom_host'], 'Google Chrome Helper'), 'ChatGPT')

    def test_wrong_google_and_missing_claude_are_repaired_without_other_rule_changes(self):
        old = {'prepend': ['DOMAIN,stun.l.google.com,DIRECT', 'DOMAIN,company.example,DIRECT'],
               'append': ['MATCH,PROXY'], 'delete': ['legacy']}
        runtime = {'rules': old['prepend'] + ['DOMAIN-KEYWORD,google,Gemini', 'MATCH,PROXY']}
        result, promoted = m.planned_rules(old, runtime, POLICY)
        self.assertEqual(m.first_target(result['prepend'], 'stun.l.google.com'), POLICY['fixed_proxy'])
        self.assertEqual(m.first_target(result['prepend'], 'claude.ai'), POLICY['claude_group'])
        self.assertIn('DOMAIN,company.example,DIRECT', result['prepend'])
        self.assertEqual(result['append'], old['append'])
        self.assertEqual(result['delete'], old['delete'])
        self.assertNotIn('DOMAIN,stun.l.google.com,DIRECT', result['prepend'])

    def test_static_matching_does_not_guess_rule_set_or_ip_outcomes(self):
        rules = ['IP-CIDR,10.0.0.0/8,DIRECT', 'DOMAIN-SUFFIX,claude.ai,' + POLICY['claude_group']]
        self.assertIsNone(m.first_target(rules, 'claude.ai'))
        self.assertEqual(m.first_target(rules, 'claude.ai', domain_only=True), POLICY['claude_group'])

    def test_valid_rules_are_idempotent(self):
        extension = {'prepend': m.requirements(POLICY), 'append': [], 'delete': []}
        runtime = {'rules': extension['prepend'] + [
            'DOMAIN-SUFFIX,' + h + ',' + POLICY['claude_group'] for h in POLICY['domain_suffixes']
        ] + ['DOMAIN,' + h + ',' + POLICY['claude_group'] for h in POLICY['exact_domains']]}
        self.assertEqual(m.planned_rules(extension, runtime, POLICY), (extension, []))

    def test_auth0_priority_conflict_gets_only_exact_host_exception(self):
        extension = {'prepend': m.requirements(POLICY), 'append': [], 'delete': []}
        runtime = {'rules': extension['prepend'] + [
            'DOMAIN-SUFFIX,auth0.com,ChatGPT', 'DOMAIN,anthropic.auth0.com,' + POLICY['claude_group']
        ] + ['DOMAIN-SUFFIX,' + h + ',' + POLICY['claude_group'] for h in POLICY['domain_suffixes']]
          + ['DOMAIN,' + h + ',' + POLICY['claude_group'] for h in POLICY['exact_domains']]}
        result, _ = m.planned_rules(extension, runtime, POLICY)
        self.assertIn('DOMAIN,anthropic.auth0.com,' + POLICY['claude_group'], result['prepend'])
        self.assertFalse(any('DOMAIN-SUFFIX,auth0.com' in r for r in result['prepend']))
        combined = result['prepend'] + runtime['rules']
        self.assertEqual(m.first_target(combined, 'anthropic.auth0.com'), POLICY['claude_group'])
        self.assertEqual(m.first_target(combined, 'unrelated.auth0.com'), 'ChatGPT')

    def test_live_rule_priority_and_and_normalization(self):
        api = [{'type':'Domain', 'payload':'stun.l.google.com', 'proxy':'DIRECT'},
               {'type':'Domain', 'payload':'stun.l.google.com', 'proxy':POLICY['fixed_proxy']},
               {'type':'AND', 'payload':'((ProcessName,Claude Helper) && (Domain,nexus-websocket-a.intercom.io))',
                'proxy':POLICY['fixed_proxy']}]
        normalized = m.api_rule_strings(api, POLICY)
        self.assertEqual(m.first_target(normalized, 'stun.l.google.com'), 'DIRECT')
        self.assertEqual(m.first_target(normalized, POLICY['intercom_host'], 'Claude Helper'), POLICY['fixed_proxy'])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.root = self.home/'clash'
        (self.root/'profiles').mkdir(parents=True)
        self.target = self.root/'profiles/dynamic-rules.yaml'
        self.original = b'prepend: []\nappend: []\ndelete: []\n'
        self.target.write_bytes(self.original)
        self.metadata = {'current':'new-uid', 'items':[
            {'uid':'new-uid','option':{'rules':'r'}}, {'uid':'r','file':'dynamic-rules.yaml'}]}
        (self.root/'profiles.yaml').write_text(yaml.safe_dump(self.metadata))
        self.runtime = {'secret':'DO-NOT-EMIT-SECRET', 'proxies': [{
            'name':POLICY['fixed_proxy'], 'type':'socks5', 'server':POLICY['proxy_server'],
            'port':POLICY['proxy_port'], 'password':'DO-NOT-EMIT-PASSWORD', 'udp':True,
            'dialer-proxy':POLICY['dialer_group']}],
            'proxy-groups':[{'name':POLICY['claude_group'],'proxies':[POLICY['fixed_proxy']]}],
            'dns':{'nameserver-policy':{'+.company.example':['10.0.0.1']}},
            'rules':['DOMAIN,company.example,DIRECT','DOMAIN,company.example,DIRECT','MATCH,PROXY']}
        (self.root/'clash-verge.yaml').write_text(yaml.safe_dump(self.runtime))
        self.home_patch = patch.object(m.Path, 'home', return_value=self.home)
        self.home_patch.start()
        self.live_patch = patch.object(m, 'live_state', return_value=None)
        self.live_patch.start()

    def tearDown(self):
        self.live_patch.stop()
        self.home_patch.stop()
        self.temp.cleanup()

    def test_repair_backup_and_conflict_safe_rollback(self):
        runtime_before = (self.root/'clash-verge.yaml').read_bytes()
        def validate(path, root):
            candidate = m.read_yaml(path)
            self.assertEqual({k:v for k,v in candidate.items() if k != 'rules'},
                             {k:v for k,v in self.runtime.items() if k != 'rules'})
            self.assertEqual(candidate['rules'].count('DOMAIN,company.example,DIRECT'), 2)
        with patch.object(m, 'validate_candidate', side_effect=validate):
            result = m.repair(m.context(self.root), POLICY)
        self.assertTrue(result['changed'])
        self.assertEqual((self.root/'clash-verge.yaml').read_bytes(), runtime_before)
        backup = Path(result['backup'])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual((backup/'original/profiles/dynamic-rules.yaml').read_bytes(), self.original)
        output = json.dumps(m.audit(m.context(self.root), POLICY, None))
        self.assertNotIn('DO-NOT-EMIT', output)
        self.target.write_bytes(self.target.read_bytes() + b'\n# later user edit\n')
        with self.assertRaises(RuntimeError):
            m.rollback(backup)
        change = json.loads((backup/'manifest.json').read_text())['rule_change']
        # Remove only this test's concurrent edit and verify ordinary rollback.
        self.target.write_bytes(self.target.read_bytes().replace(b'\n# later user edit\n', b''))
        self.assertEqual(m.digest(self.target.read_bytes()), change['after'])
        m.rollback(backup)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_failed_validation_keeps_source_untouched(self):
        with patch.object(m, 'validate_candidate', side_effect=RuntimeError('validation failed')):
            with self.assertRaises(RuntimeError):
                m.repair(m.context(self.root), POLICY)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_rule_source_path_escape_is_refused(self):
        self.metadata['items'][1]['file'] = '../../escape.yaml'
        (self.root/'profiles.yaml').write_text(yaml.safe_dump(self.metadata))
        with self.assertRaises(ValueError):
            m.context(self.root)

    def test_default_invocation_is_read_only_even_with_dns_findings(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        allowed = {('/usr/bin/defaults', 'read', '-g', 'AppleLanguages'),
                   ('/usr/bin/defaults', 'read', '-g', 'AppleLocale'),
                   ('/usr/bin/defaults', 'read', 'com.anthropic.claudefordesktop', 'AppleLanguages'),
                   ('/sbin/ifconfig', '-a'), ('/usr/sbin/networksetup', '-listnetworkserviceorder'),
                   ('/sbin/route', '-n', 'get', 'default'), ('/sbin/route', '-n', 'get', '-inet6', 'default')}
        def read_command(arguments, **kwargs):
            self.assertIn(tuple(arguments), allowed)
            self.assertNotIn('shell', kwargs)
            return m.subprocess.CompletedProcess(arguments, 1, '', 'unavailable')
        with patch.object(m.sys, 'argv', ['check_claude.py', '--config-dir', str(self.root)]), \
                patch.object(m, 'repair') as repair, \
                patch.object(m.subprocess, 'run', side_effect=read_command) as command, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(), 2)
        repair.assert_not_called()
        command.assert_called()
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        report = json.loads(output.getvalue())
        self.assertEqual(report['dns']['actual_test_status'], 'NOT_RUN')
        self.assertEqual(report['dns']['company_access_status'], 'NOT_TESTED')


class DesktopAuxiliaryTests(unittest.TestCase):
    def setUp(self):
        self.rules = m.requirements(POLICY) + m.auxiliary_rules(POLICY)
        self.extension = {'prepend': list(self.rules), 'append': [], 'delete': []}
        self.runtime = {'rules': self.rules + ['DOMAIN-SUFFIX,intercom.io,ChatGPT', 'MATCH,US01']}
        self.api_rules = []
        for rule in self.rules:
            parts = m.split_rule(rule)
            self.api_rules.append({'type': 'AND' if parts[0] == 'AND' else 'Domain',
                                   'payload': m.logical_api_payload(parts[1]), 'proxy': parts[2]})
        self.api_rules += [{'type': 'DomainSuffix', 'payload': 'intercom.io', 'proxy': 'ChatGPT'},
                           {'type': 'Match', 'payload': '', 'proxy': 'US01'}]

    def connection(self, host='widget.intercom.io', process='Claude Helper', path=None, fixed=True):
        return {'metadata': {'host': host, 'process': process,
                             'processPath': '/Applications/Claude.app/Contents/MacOS/Claude Helper' if path is None else path},
                'chains': [POLICY['fixed_proxy']] if fixed else ['US01'], 'upload': 20, 'download': 30}

    def run_audit(self, rows=(), live_available=True):
        live = {'rules': {'rules': self.api_rules}, 'connections': {'connections': list(rows)}} if live_available else None
        return m.audit_desktop_auxiliary(self.extension, self.runtime, POLICY, live)

    def test_scope_preserves_other_apps_and_unselected_intercom_hosts(self):
        for host in ('widget.intercom.io', 'hcaptcha.com', 'random.w.hcaptcha.com'):
            self.assertEqual(m.first_target(self.runtime['rules'], host, 'Claude Helper'), POLICY['fixed_proxy'])
            for process in ('Google Chrome Helper', 'ChatGPT', 'Claude Code', ''):
                self.assertNotEqual(m.first_target(self.runtime['rules'], host, process), POLICY['fixed_proxy'])
        for host in ('api-iam.intercom.io', 'widget.intercom.io.example.com', 'hcaptcha.com.example.com'):
            self.assertNotEqual(m.first_target(self.runtime['rules'], host, 'Claude Helper'), POLICY['fixed_proxy'])

    def test_empty_snapshot_keeps_hcaptcha_pending_despite_valid_configuration(self):
        checks, report = self.run_audit()
        self.assertTrue(all(c['status'] == 'PASS' for c in checks))
        self.assertEqual(report['configuration_status'], 'PASS')
        self.assertEqual(report['active_test_status'], 'NOT_RUN')
        for label in ('widget', 'hcaptcha'):
            self.assertEqual(report['targets'][label]['actual_traffic_status'], 'UNVERIFIED')
            self.assertEqual(report['targets'][label]['observation_status'], 'NO_MATCHES_IN_SNAPSHOT')

    def test_missing_api_does_not_report_live_or_traffic_success(self):
        checks, report = self.run_audit(live_available=False)
        self.assertIn('UNVERIFIED', {c['status'] for c in checks})
        self.assertEqual(report['targets']['hcaptcha']['observation_status'], 'UNAVAILABLE')
        self.assertEqual(report['targets']['hcaptcha']['actual_traffic_status'], 'UNVERIFIED')

    def test_domain_suffix_and_normalized_live_rules_keep_priority_checks_usable(self):
        normalized = m.api_rule_strings(self.api_rules, POLICY)
        self.assertEqual(m.first_target(normalized, 'random.w.hcaptcha.com', 'Claude Helper'), POLICY['fixed_proxy'])
        self.assertEqual(m.first_target(normalized, 'widget.intercom.io', 'Google Chrome Helper'), 'ChatGPT')
        self.assertEqual(m.first_target(normalized, POLICY['intercom_host'], 'Claude Helper'), POLICY['fixed_proxy'])

    def test_disabled_or_shadowed_rules_are_detected(self):
        for case in ('disabled', 'shadowed'):
            with self.subTest(case=case):
                saved = copy.deepcopy(self.api_rules)
                if case == 'disabled':
                    self.api_rules[-3]['extra'] = {'disabled': True}
                else:
                    self.api_rules.insert(0, {'type': 'Domain', 'payload': 'widget.intercom.io', 'proxy': 'DIRECT'})
                checks, report = self.run_audit()
                self.assertIn('FAIL', {c['status'] for c in checks})
                self.assertEqual(report['configuration_status'], 'ATTENTION')
                self.api_rules = saved

    def test_only_verified_desktop_bidirectional_samples_pass(self):
        for path, status in (('/Applications/Claude.app/Contents/MacOS/Claude Helper', 'PASS'),
                             ('', 'UNVERIFIED'), ('/Applications/Other.app/Claude Helper', 'UNVERIFIED')):
            with self.subTest(path=path):
                _, report = self.run_audit([self.connection(path=path)])
                self.assertEqual(report['targets']['widget']['actual_traffic_status'], status)
                self.assertEqual(report['targets']['hcaptcha']['actual_traffic_status'], 'UNVERIFIED')

    def test_hcaptcha_requires_current_traffic_and_reports_nonfixed_failure(self):
        for fixed, download, status in ((True, 30, 'PASS'), (True, 0, 'UNVERIFIED'), (False, 30, 'FAIL')):
            row = self.connection(host='new.w.hcaptcha.com', fixed=fixed)
            row['download'] = download
            checks, report = self.run_audit([row])
            self.assertEqual(report['targets']['hcaptcha']['actual_traffic_status'], status)
            self.assertEqual(report['active_test_status'], 'NOT_RUN')
            if not fixed:
                self.assertIn('FAIL', {c['status'] for c in checks})

    def test_other_apps_and_hostname_lookalikes_do_not_become_desktop_evidence(self):
        rows = [self.connection(process='Google Chrome Helper', fixed=False),
                self.connection(host='api-iam.intercom.io'),
                self.connection(host='sub.widget.intercom.io'),
                self.connection(host='hcaptcha.com.example.com')]
        checks, report = self.run_audit(rows)
        self.assertTrue(all(c['status'] == 'PASS' for c in checks))
        self.assertEqual(report['targets']['widget']['other_process_sample_count'], 1)
        self.assertEqual(report['targets']['widget']['connections'], [])
        self.assertEqual(report['targets']['hcaptcha']['connections'], [])

    def test_broad_fixed_domain_rules_are_flagged(self):
        broad = 'DOMAIN-SUFFIX,hcaptcha.com,' + POLICY['fixed_proxy']
        self.extension['prepend'].append(broad)
        self.runtime['rules'].append(broad)
        checks, _ = self.run_audit()
        statuses = {c['item']: c['status'] for c in checks}
        self.assertEqual(statuses['desktop_aux_scope:persistent'], 'FAIL')
        self.assertEqual(statuses['desktop_aux_scope:generated'], 'FAIL')

    def test_observation_never_performs_io_mutates_or_emits_sensitive_metadata(self):
        row = self.connection(host='DO-NOT-EMIT.w.hcaptcha.com')
        row['metadata'].update({'url': 'DO-NOT-EMIT', 'password': 'DO-NOT-EMIT'})
        saved = copy.deepcopy((self.extension, self.runtime, self.api_rules, row))
        with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
            checks, report = self.run_audit([row])
        network.assert_not_called()
        command.assert_not_called()
        self.assertEqual((self.extension, self.runtime, self.api_rules, row), saved)
        self.assertNotIn('DO-NOT-EMIT', json.dumps((checks, report)))

    def test_auxiliary_baseline_does_not_expand_automatic_repair(self):
        extension = {'prepend': m.requirements(POLICY), 'append': [], 'delete': []}
        runtime = {'rules': extension['prepend'] + [
            'DOMAIN-SUFFIX,' + h + ',' + POLICY['claude_group'] for h in POLICY['domain_suffixes']
        ] + ['DOMAIN,' + h + ',' + POLICY['claude_group'] for h in POLICY['exact_domains']]}
        self.assertEqual(m.planned_rules(extension, runtime, POLICY), (extension, []))


class DNSPathObservationTests(unittest.TestCase):
    def connection(self, host='', address='1.1.1.1', port='443', chains=None,
                   process='Google Chrome Helper', network='tcp'):
        return {'metadata': {'host': host, 'destinationIP': address, 'destinationPort': port,
                             'process': process, 'network': network},
                'chains': ['OTHER'] if chains is None else chains, 'upload': 20, 'download': 30}

    def observe(self, *connections):
        return m.observe_dns_paths({'connections': {'connections': list(connections)}}, POLICY)

    def test_missing_or_empty_snapshot_is_not_proof_of_no_leak(self):
        for live in (None, {}, {'connections': {}}):
            with self.subTest(live=live):
                report = m.observe_dns_paths(live, POLICY)
                self.assertEqual(report['observation_status'], 'UNAVAILABLE')
                self.assertEqual(report['resolver_origin_status'], 'UNVERIFIED')
                self.assertEqual(report['actual_comparison_status'], 'NOT_RUN')
        report = self.observe()
        self.assertEqual(report['observation_status'], 'NO_MATCHES_IN_SNAPSHOT')
        self.assertEqual(report['resolver_origin_status'], 'UNVERIFIED')

    def test_chrome_https_to_cloudflare_is_not_automatically_doh_or_leak(self):
        report = self.observe(self.connection())
        row = report['connections'][0]
        self.assertEqual(row['kind'], 'RESOLVER_ENDPOINT_PURPOSE_UNVERIFIED')
        self.assertEqual(row['route'], 'OTHER_PROXY')
        self.assertEqual(row['client'], 'CHROME')
        self.assertEqual(report['resolver_origin_status'], 'UNVERIFIED')

    def test_fixed_resolver_endpoint_does_not_prove_every_dns_path_is_fixed(self):
        report = self.observe(self.connection(chains=[POLICY['fixed_proxy']]))
        self.assertEqual(report['connections'][0]['route'], 'FIXED')
        self.assertTrue(report['connections'][0]['bidirectional'])
        self.assertEqual(report['actual_comparison_status'], 'NOT_RUN')
        self.assertEqual(report['resolver_origin_status'], 'UNVERIFIED')

    def test_google_endpoint_still_requires_payload_and_attribution_evidence(self):
        for port in (53, 443, 853):
            with self.subTest(port=port):
                report = self.observe(self.connection(host='dns.google', address='8.8.8.8',
                                                      port=port, chains=['DIRECT']))
                self.assertEqual(report['connections'][0]['endpoint'], 'dns.google')
                self.assertEqual(report['connections'][0]['route'], 'DIRECT')
                self.assertEqual(report['connections'][0]['kind'], 'RESOLVER_ENDPOINT_PURPOSE_UNVERIFIED')
                self.assertEqual(report['resolver_origin_status'], 'UNVERIFIED')

    def test_random_probe_route_is_separate_from_resolver_identity(self):
        for chains, route in (([POLICY['fixed_proxy']], 'FIXED'), (['DIRECT'], 'DIRECT'),
                              (['US01', 'GROUP'], 'OTHER_PROXY'), ([], 'UNKNOWN')):
            with self.subTest(route=route):
                report = self.observe(self.connection(host='sample-1.d.ip.net.coffee',
                                                      address='188.253.118.226', chains=chains))
                self.assertEqual(report['connections'][0]['kind'], 'DNS_TEST_HTTPS')
                self.assertEqual(report['connections'][0]['route'], route)
                self.assertEqual(report['resolver_origin_status'], 'UNVERIFIED')

    def test_unrelated_domains_ports_and_suffix_lookalikes_are_ignored(self):
        rows = [self.connection(host=h, address='192.0.2.1') for h in
                ('claude.ai', 'email.ziyondpharma.com', 'sample.d.ip.net.coffee.example.com',
                 'private.sample.d.ip.net.coffee')]
        rows.append(self.connection(port=80))
        report = self.observe(*rows)
        self.assertEqual(report['connections'], [])
        self.assertEqual(report['observation_status'], 'NO_MATCHES_IN_SNAPSHOT')

    def test_observation_does_not_emit_unselected_metadata_or_secret_urls(self):
        row = self.connection(process='DO-NOT-EMIT-SECRET', chains=['DO-NOT-EMIT-SECRET'])
        row['metadata']['url'] = 'https://user:DO-NOT-EMIT-SECRET@1.1.1.1/dns-query'
        row['metadata']['password'] = 'DO-NOT-EMIT-SECRET'
        row['secret'] = 'DO-NOT-EMIT-SECRET'
        report = self.observe(row)
        self.assertNotIn('DO-NOT-EMIT', json.dumps(report))
        self.assertEqual(report['connections'][0]['client'], 'OTHER')
        self.assertEqual(report['connections'][0]['route'], 'OTHER_PROXY')

    def test_observation_never_queries_executes_or_mutates_input(self):
        live = {'connections': {'connections': [self.connection()]}}
        before = copy.deepcopy(live)
        with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
            report = m.observe_dns_paths(live, POLICY)
        network.assert_not_called()
        command.assert_not_called()
        self.assertEqual(live, before)
        self.assertEqual(report['observation_status'], 'OBSERVED')


class ClaudeDNSPathObservationTests(unittest.TestCase):
    def connection(self, host='api.anthropic.com', chains=None, address='160.79.104.10'):
        return {'metadata': {'host': host, 'network': 'tcp', 'destinationIP': address},
                'chains': [POLICY['fixed_proxy']] if chains is None else chains,
                'upload': 12, 'download': 34}

    def observe(self, *connections):
        return m.observe_claude_dns_path({'connections': {'connections': list(connections)}}, POLICY)

    def test_missing_and_empty_samples_cannot_establish_no_bypass(self):
        for live in (None, {}, {'connections': {}}, {'connections': {'connections': []}}):
            report = m.observe_claude_dns_path(live, POLICY)
            self.assertIn(report['observation_status'], ('UNAVAILABLE', 'NO_MATCHES_IN_SNAPSHOT'))
            self.assertEqual(report['dns_path_status'], 'UNVERIFIED')
            self.assertEqual(sum(report['route_counts'].values()), 0)

    def test_fixed_business_route_does_not_pass_dns_or_tls_tests(self):
        report = self.observe(self.connection())
        self.assertEqual(report['route_counts']['FIXED'], 1)
        self.assertTrue(report['connections'][0]['bidirectional'])
        self.assertEqual(report['dns_path_status'], 'UNVERIFIED')
        for field in ('actual_test_status', 'tls_test_status', 'authoritative_comparison_status'):
            self.assertEqual(report[field], 'NOT_RUN')

    def test_nonfixed_samples_are_visible_without_automatic_dns_attribution(self):
        report = self.observe(*(self.connection(chains=c) for c in
                                ([POLICY['fixed_proxy'], 'UPSTREAM'], ['DIRECT'], ['US01'], [])))
        self.assertEqual(report['route_counts'], dict.fromkeys(('FIXED', 'DIRECT', 'OTHER_PROXY', 'UNKNOWN'), 1))
        self.assertEqual(report['dns_path_status'], 'UNVERIFIED')

    def test_domain_boundaries_exclude_business_exceptions_and_suffix_lookalikes(self):
        hosts = ('CLAUDE.AI.', 'anthropic.auth0.com', 'claude.ai.evil.example',
                 'sub.anthropic.auth0.com', 'email.ziyondpharma.com', 'docs.feishu.cn',
                 'stun.cloudflare.com', POLICY['intercom_host'])
        report = self.observe(*(self.connection(host=h) for h in hosts))
        self.assertEqual([row['host_scope'] for row in report['connections']],
                         ['claude.ai', 'anthropic.auth0.com'])

    def test_ipv6_destination_is_only_connection_metadata(self):
        report = self.observe(self.connection(address='2607:6bc0::10'))
        self.assertTrue(report['connections'][0]['ipv6_destination_observed'])
        self.assertEqual(report['dns_path_status'], 'UNVERIFIED')
        self.assertEqual(report['actual_test_status'], 'NOT_RUN')

    def test_no_io_input_mutation_or_sensitive_metadata_output(self):
        connection = self.connection(host='DO-NOT-EMIT.claude.ai', chains=[POLICY['fixed_proxy'], 'DO-NOT-EMIT'])
        connection['metadata'].update({'process': 'DO-NOT-EMIT', 'url': 'DO-NOT-EMIT', 'password': 'DO-NOT-EMIT'})
        live = {'connections': {'connections': [connection]}}
        before = copy.deepcopy(live)
        with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
            report = m.observe_claude_dns_path(live, POLICY)
        network.assert_not_called()
        command.assert_not_called()
        self.assertEqual(live, before)
        self.assertNotIn('DO-NOT-EMIT', json.dumps(report))
        self.assertEqual(report['connections'][0]['host_scope'], 'claude.ai')


class DNSTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'profiles').mkdir()
        dns = POLICY['dns']
        self.source = self.root/dns['persistent_script']
        self.source.write_text('function main(config) {\n'
                               + 'const domain = "email.ziyondpharma.com";\n'
                               + 'config.hosts = { ...(config.hosts || {}) };\n'
                               + 'delete config.hosts[domain];\n'
                               + 'config.dns.nameserver = '
                               + json.dumps(dns['public_nameservers'])
                               + '; config.dns["nameserver-policy"] = '
                               + json.dumps({**dns['feishu_nameserver_policy'],
                                             **dns['company_public_nameserver_policy'],
                                             **dns['company_wifi_nameserver_policy']}) + '; return config; }')
        self.runtime = {
            'dns': {'enable': True, 'nameserver': list(dns['public_nameservers']),
                    'nameserver-policy': {'+.' + dns['company_domain']: list(dns['company_nameservers']),
                                          **copy.deepcopy(dns['feishu_nameserver_policy']),
                                          **copy.deepcopy(dns['company_public_nameserver_policy']),
                                          **copy.deepcopy(dns['company_wifi_nameserver_policy'])},
                    'fake-ip-filter': ['+.' + dns['company_domain']], 'use-hosts': True,
                    'default-nameserver': ['223.5.5.5'],
                    'proxy-server-nameserver': ['https://doh.pub/dns-query']},
            'hosts': dict(dns['company_hosts']),
            'rules': ['DOMAIN-SUFFIX,' + dns['company_domain'] + ',DIRECT', 'MATCH,PROXY'],
            'tun': {'dns-hijack': ['any:53']},
        }

    def tearDown(self):
        self.temp.cleanup()

    def statuses(self):
        checks, summary = m.audit_dns(self.root, self.runtime, POLICY)
        return {x['item']: x['status'] for x in checks}, summary

    def test_private_company_and_domestic_bootstrap_are_exempt_without_network_io(self):
        before = copy.deepcopy(self.runtime)
        with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
            states, summary = self.statuses()
        self.assertTrue(all(x == 'PASS' for x in states.values()))
        self.assertEqual(summary['configuration_status'], 'PASS')
        self.assertEqual(summary['bootstrap_exception']['status'], 'EXEMPT')
        self.assertEqual(summary['actual_test_status'], 'NOT_RUN')
        self.assertEqual(summary['company_access_status'], 'NOT_TESTED')
        self.assertEqual(summary['feishu_exception']['status'], 'EXEMPT')
        self.assertEqual(summary['feishu_exception']['actual_test_status'], 'NOT_RUN')
        self.assertEqual(summary['mail_dns']['status'], 'PASS')
        self.assertEqual(summary['mail_dns']['actual_test_status'], 'NOT_RUN')
        self.assertEqual(summary['mail_dns']['cache_test_status'], 'NOT_RUN')
        self.assertEqual(summary['mail_dns']['connection_test_status'], 'NOT_RUN')
        self.assertEqual(summary['mail_dns']['policy_domains'], ['email.ziyondpharma.com'])
        self.assertEqual(summary['company_unpinned_hosts']['status'], 'PASS')
        self.assertEqual(summary['company_unpinned_hosts']['actual_test_status'], 'NOT_RUN')
        self.assertEqual(summary['company_wifi_dns']['status'], 'EXEMPT')
        for field in ('actual_test_status', 'cache_test_status', 'browser_test_status'):
            self.assertEqual(summary['company_wifi_dns'][field], 'NOT_RUN')
        self.assertEqual(self.runtime, before)
        network.assert_not_called()
        command.assert_not_called()

    def test_existing_business_guards_pass_with_other_proxy_test_observations(self):
        live = {'rules': {'rules': [{'type': 'DomainSuffix', 'payload': 'ziyondpharma.com',
                                    'proxy': 'DIRECT'}]},
                'connections': {'connections': [{
                    'metadata': {'host': 'sample-1.d.ip.net.coffee', 'destinationIP': '192.0.2.1',
                                 'destinationPort': '443', 'network': 'tcp'},
                    'chains': ['US01'], 'upload': 5, 'download': 6}]}}
        checks, summary = m.audit_dns(self.root, self.runtime, POLICY, live)
        self.assertTrue(all(row['status'] == 'PASS' for row in checks))
        self.assertEqual(summary['configuration_status'], 'PASS')
        self.assertEqual(summary['mail_dns']['status'], 'PASS')
        self.assertEqual(summary['feishu_exception']['status'], 'EXEMPT')
        self.assertEqual(summary['company_wifi_dns']['status'], 'EXEMPT')
        self.assertEqual(summary['actual_test_status'], 'NOT_RUN')
        self.assertEqual(summary['resolver_path_observations']['connections'][0]['route'], 'OTHER_PROXY')
        self.assertEqual(summary['resolver_path_observations']['resolver_origin_status'], 'UNVERIFIED')

    def test_system_primary_and_fallback_are_detected_without_changing_them(self):
        self.runtime['dns']['nameserver'] = ['system']
        self.runtime['dns']['fallback'] = ['system']
        before = copy.deepcopy(self.runtime)
        states, _ = self.statuses()
        self.assertEqual(states['dns_public_encrypted_fixed_route'], 'FAIL')
        self.assertEqual(states['dns_other_public_paths'], 'FAIL')
        self.assertEqual(self.runtime, before)

    def test_claude_snapshot_keeps_business_checks_and_active_test_status_separate(self):
        connection = ClaudeDNSPathObservationTests().connection()
        live = {'rules': {'rules': [{'type': 'DomainSuffix', 'payload': 'ziyondpharma.com',
                                    'proxy': 'DIRECT'}]},
                'connections': {'connections': [connection]}}
        checks, summary = m.audit_dns(self.root, self.runtime, POLICY, live)
        self.assertTrue(all(row['status'] == 'PASS' for row in checks))
        self.assertEqual(summary['claude_path_observations']['route_counts']['FIXED'], 1)
        self.assertEqual(summary['claude_path_observations']['dns_path_status'], 'UNVERIFIED')
        self.assertEqual(summary['actual_test_status'], 'NOT_RUN')
        self.assertEqual(summary['company_wifi_dns']['status'], 'EXEMPT')
        self.assertEqual(summary['mail_dns']['status'], 'PASS')
        self.assertEqual(summary['feishu_exception']['status'], 'EXEMPT')
        self.assertEqual(summary['company_access_status'], 'NOT_TESTED')

    def test_wifi_policy_missing_or_changed_keeps_private_and_public_main_dns_checked(self):
        values = [None, [], ['system'], ['dhcp://system'], ['dhcp://en1'],
                  POLICY['dns']['public_nameservers'], POLICY['dns']['company_nameservers'],
                  ['dhcp://en0', 'system'], ['dhcp://en0#DIRECT'], ['dhcp://en0?x=1']]
        for host in POLICY['dns']['company_wifi_nameserver_policy']:
            for value in values:
                with self.subTest(host=host, value=value):
                    saved = copy.deepcopy(self.runtime)
                    policies = self.runtime['dns']['nameserver-policy']
                    if value is None:
                        policies.pop(host)
                    else:
                        policies[host] = value
                    before = copy.deepcopy(self.runtime)
                    states, summary = self.statuses()
                    self.assertEqual(states['dns_company_wifi_upstreams'], 'FAIL')
                    self.assertEqual(states['dns_public_baseline'], 'PASS')
                    self.assertEqual(states['dns_company_upstreams'], 'PASS')
                    self.assertEqual(summary['company_wifi_dns']['status'], 'ATTENTION')
                    self.assertEqual(self.runtime, before)
                    self.runtime = saved

    def test_wifi_exception_cannot_expand_to_other_domains(self):
        for host in ('+.oa.ziyondpharma.com', 'sub.oa.ziyondpharma.com',
                     'hr.ziyondpharma.com', '+.ziyondpharma.com', '+.claude.ai',
                     '+.feishu.cn', '+.email.ziyondpharma.com', 'sub.email.ziyondpharma.com'):
            with self.subTest(host=host):
                saved = copy.deepcopy(self.runtime)
                self.runtime['dns']['nameserver-policy'][host] = ['dhcp://en0']
                states, _ = self.statuses()
                item = 'dns_company_upstreams' if host == '+.ziyondpharma.com' else 'dns_other_public_paths'
                self.assertEqual(states[item], 'FAIL')
                self.runtime = saved

    def test_dhcp_not_exempt_in_primary_fallback_or_direct_resolvers(self):
        for field in ('nameserver', 'fallback', 'direct-nameserver'):
            with self.subTest(field=field):
                saved = copy.deepcopy(self.runtime)
                self.runtime['dns'][field] = ['dhcp://en0']
                states, _ = self.statuses()
                item = 'dns_public_encrypted_fixed_route' if field == 'nameserver' else 'dns_other_public_paths'
                self.assertEqual(states[item], 'FAIL')
                self.assertEqual(states['dns_company_wifi_upstreams'], 'PASS')
                self.runtime = saved

    def test_stale_wifi_source_detected_without_execution_or_queries(self):
        self.source.write_text(self.source.read_text().replace('dhcp://en0', 'system'))
        with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
            states, _ = self.statuses()
        self.assertEqual(states['dns_company_wifi_upstreams'], 'PASS')
        self.assertEqual(states['dns_company_wifi_persistent_source'], 'FAIL')
        self.assertEqual(states['dns_mail_wifi_persistent_source'], 'FAIL')
        network.assert_not_called()
        command.assert_not_called()

    def test_unknown_duplicate_or_malformed_wifi_source_is_unverified(self):
        original = self.source.read_text()
        host = 'oa.ziyondpharma.com'
        declaration = json.dumps(host) + ': ["dhcp://en0"]'
        self.assertIn(declaration, original)
        variants = [original.replace(declaration, json.dumps(host) + ': buildResolvers()'),
                    original + '\nconst other = {' + declaration + '};',
                    original.replace(declaration, json.dumps(host) + ': [INVALID]')]
        for source in variants:
            with self.subTest(source_variant=variants.index(source)):
                self.source.write_text(source)
                states, _ = self.statuses()
                self.assertEqual(states['dns_company_wifi_upstreams'], 'PASS')
                self.assertEqual(states['dns_company_wifi_persistent_source'], 'UNVERIFIED')

    def test_wifi_hosts_must_not_be_pinned_to_private_or_public_addresses(self):
        for host in POLICY['dns']['company_wifi_nameserver_policy']:
            for ip in ('192.168.10.13', '221.131.102.242'):
                with self.subTest(host=host, ip=ip):
                    self.runtime['hosts'][host] = ip
                    before = copy.deepcopy(self.runtime)
                    states, _ = self.statuses()
                    self.assertEqual(states['dns_company_wifi_unpinned_hosts'], 'FAIL')
                    self.assertEqual(states['dns_company_unpinned_hosts'],
                                     'FAIL' if host == 'email.ziyondpharma.com' else 'PASS')
                    self.assertEqual(self.runtime, before)
                    del self.runtime['hosts'][host]

    def test_wifi_hosts_still_require_generated_and_live_direct_routes(self):
        for host in POLICY['dns']['company_wifi_nameserver_policy']:
            with self.subTest(host=host):
                saved = copy.deepcopy(self.runtime)
                self.runtime['rules'].insert(0, 'DOMAIN,' + host + ',PROXY')
                live = {'rules': {'rules': [
                    {'type': 'Domain', 'payload': host, 'proxy': 'PROXY'},
                    {'type': 'DomainSuffix', 'payload': 'ziyondpharma.com', 'proxy': 'DIRECT'}]}}
                checks, _ = m.audit_dns(self.root, self.runtime, POLICY, live)
                states = {x['item']: x['status'] for x in checks}
                self.assertEqual(states['dns_company_direct_rules'], 'FAIL')
                self.assertEqual(states['dns_company_live_direct_rules'], 'FAIL')
                self.runtime = saved

    def test_mail_wifi_hosts_missing_or_changed_policy_is_detected(self):
        values = [None, [], ['system'], POLICY['dns']['company_nameservers'],
                  ['https://dns.alidns.com/dns-query'],
                  POLICY['dns']['public_nameservers'][:1],
                  ['https://1.1.1.1/dns-query#DIRECT'],
                  POLICY['dns']['public_nameservers'] + ['system']]
        for host in ('email.ziyondpharma.com',):
            original = self.runtime['dns']['nameserver-policy'][host]
            for value in values:
                with self.subTest(host=host, value=value):
                    if value is None:
                        self.runtime['dns']['nameserver-policy'].pop(host)
                    else:
                        self.runtime['dns']['nameserver-policy'][host] = value
                    states, summary = self.statuses()
                    self.assertEqual(states['dns_mail_wifi_upstreams'], 'FAIL')
                    self.assertEqual(states['dns_company_upstreams'], 'PASS')
                    self.assertEqual(summary['mail_dns']['status'], 'ATTENTION')
                    self.assertEqual(summary['mail_dns']['actual_test_status'], 'NOT_RUN')
                    self.runtime['dns']['nameserver-policy'][host] = original

    def test_company_public_override_cannot_expand_to_other_company_names(self):
        for host in ('+.oa.ziyondpharma.com', 'sub.oa.ziyondpharma.com',
                     '+.email.ziyondpharma.com', 'sub.email.ziyondpharma.com',
                     'hr.ziyondpharma.com', '+.ziyondpharma.com'):
            with self.subTest(host=host):
                saved = copy.deepcopy(self.runtime)
                self.runtime['dns']['nameserver-policy'][host] = POLICY['dns']['public_nameservers']
                states, _ = self.statuses()
                item = 'dns_company_upstreams' if host == '+.ziyondpharma.com' else 'dns_company_other_policy_scope'
                self.assertEqual(states[item], 'FAIL')
                self.runtime = saved

    def test_mail_wifi_suffix_cannot_replace_exact_host_policy(self):
        for host in ('email.ziyondpharma.com',):
            with self.subTest(host=host):
                saved = copy.deepcopy(self.runtime)
                policies = self.runtime['dns']['nameserver-policy']
                policies['+.' + host] = policies.pop(host)
                states, _ = self.statuses()
                self.assertEqual(states['dns_mail_wifi_upstreams'], 'FAIL')
                self.assertEqual(states['dns_company_other_policy_scope'], 'FAIL')
                self.runtime = saved

    def test_mail_static_private_or_public_mapping_is_detected_without_mutation(self):
        host = 'email.ziyondpharma.com'
        for ip in ('10.8.100.101', '61.160.91.22'):
            with self.subTest(ip=ip):
                self.runtime['hosts'][host] = ip
                before = copy.deepcopy(self.runtime)
                states, summary = self.statuses()
                self.assertEqual(states['dns_company_unpinned_hosts'], 'FAIL')
                self.assertEqual(summary['company_unpinned_hosts']['status'], 'ATTENTION')
                self.assertEqual(summary['company_unpinned_hosts']['actual_test_status'], 'NOT_RUN')
                self.assertEqual(self.runtime, before)

    def test_mail_unpin_source_requires_known_deletion_without_execution(self):
        original = self.source.read_text()
        changes = [original.replace('delete config.hosts[domain];', ''),
                   original.replace('delete config.hosts[domain];', 'config.hosts[domain] = "10.8.100.101";'),
                   original.replace('delete config.hosts[domain];', 'removeMailHost(config);'),
                   original + '\nconfig.hosts["email.ziyondpharma.com"] = "10.8.100.101";']
        for text in changes:
            with self.subTest(text=text):
                self.source.write_text(text)
                with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
                    states, summary = self.statuses()
                self.assertEqual(states['dns_company_unpinned_hosts'], 'PASS')
                self.assertEqual(states['dns_mail_wifi_persistent_source'], 'PASS')
                self.assertEqual(states['dns_company_unpinned_persistent_source'], 'UNVERIFIED')
                self.assertEqual(summary['configuration_status'], 'ATTENTION')
                network.assert_not_called()
                command.assert_not_called()

    def test_mail_unpin_source_invalid_json_literal_does_not_crash(self):
        self.source.write_text(self.source.read_text().replace(
            'const domain = "email.ziyondpharma.com";', 'const domain = "\\q";'))
        states, _ = self.statuses()
        self.assertEqual(states['dns_company_unpinned_persistent_source'], 'UNVERIFIED')

    def test_mail_generated_and_live_direct_route_remain_required(self):
        host = 'email.ziyondpharma.com'
        self.runtime['rules'].insert(0, 'DOMAIN,' + host + ',PROXY')
        states, _ = self.statuses()
        self.assertEqual(states['dns_company_direct_rules'], 'FAIL')
        live = {'rules': {'rules': [
            {'type': 'Domain', 'payload': host, 'proxy': 'PROXY'},
            {'type': 'DomainSuffix', 'payload': POLICY['dns']['company_domain'], 'proxy': 'DIRECT'}]}}
        checks, _ = m.audit_dns(self.root, self.runtime, POLICY, live)
        self.assertEqual(next(x['status'] for x in checks if x['item']=='dns_company_live_direct_rules'), 'FAIL')

    def test_other_approved_company_hosts_are_still_protected(self):
        policy = copy.deepcopy(POLICY)
        host = 'internal.ziyondpharma.com'
        policy['dns']['company_hosts'][host] = '10.8.100.102'
        self.runtime['hosts'][host] = '10.8.100.102'
        checks, _ = m.audit_dns(self.root, self.runtime, policy)
        self.assertEqual(next(x['status'] for x in checks if x['item']=='dns_company_hosts'), 'PASS')
        del self.runtime['hosts'][host]
        checks, _ = m.audit_dns(self.root, self.runtime, policy)
        self.assertEqual(next(x['status'] for x in checks if x['item']=='dns_company_hosts'), 'FAIL')

    def test_stale_mail_source_is_detected_without_execution(self):
        original = self.source.read_text()
        for host in ('email.ziyondpharma.com',):
            with self.subTest(host=host):
                declaration = json.dumps(host) + ': ' + json.dumps(POLICY['dns']['company_wifi_nameserver_policy'][host])
                self.source.write_text(original.replace(declaration, json.dumps(host) + ': ["system"]'))
                with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
                    states, _ = self.statuses()
                self.assertEqual(states['dns_mail_wifi_upstreams'], 'PASS')
                self.assertEqual(states['dns_mail_wifi_persistent_source'], 'FAIL')
                self.assertEqual(states['dns_persistent_source'], 'PASS')
                network.assert_not_called()
                command.assert_not_called()

    def test_unknown_mail_source_is_unverified_despite_valid_runtime(self):
        text = self.source.read_text()
        for host in ('email.ziyondpharma.com',):
            text = text.replace(json.dumps(host), json.dumps('other.' + host))
        self.source.write_text(text)
        states, summary = self.statuses()
        self.assertEqual(states['dns_mail_wifi_upstreams'], 'PASS')
        self.assertEqual(states['dns_mail_wifi_persistent_source'], 'UNVERIFIED')
        self.assertEqual(summary['configuration_status'], 'ATTENTION')

    def test_mail_old_public_policy_and_secret_urls_are_rejected_without_emitting_secrets(self):
        for value in (POLICY['dns']['public_nameservers'],
                      ['https://user:DO-NOT-EMIT@example.test/dns-query?token=DO-NOT-EMIT']):
            with self.subTest(old_public=value == POLICY['dns']['public_nameservers']):
                self.runtime['dns']['nameserver-policy']['email.ziyondpharma.com'] = value
                checks, summary = m.audit_dns(self.root, self.runtime, POLICY)
                states = {x['item']: x['status'] for x in checks}
                self.assertEqual(states['dns_mail_wifi_upstreams'], 'FAIL')
                self.assertEqual(summary['mail_dns']['status'], 'ATTENTION')
                self.assertNotIn('DO-NOT-EMIT', json.dumps([checks, summary]))

    def test_other_company_policy_scope_stays_checked_without_public_exceptions(self):
        self.assertEqual(POLICY['dns']['company_public_nameserver_policy'], {})
        for value in (['dhcp://en0'], POLICY['dns']['public_nameservers']):
            with self.subTest(resolver=value):
                self.runtime['dns']['nameserver-policy']['hr.ziyondpharma.com'] = value
                states, _ = self.statuses()
                self.assertEqual(states['dns_company_other_policy_scope'], 'FAIL')
                self.assertEqual(states['dns_mail_wifi_upstreams'], 'PASS')
        self.runtime['dns']['nameserver-policy']['hr.ziyondpharma.com'] = POLICY['dns']['company_nameservers']
        states, _ = self.statuses()
        self.assertEqual(states['dns_company_other_policy_scope'], 'PASS')

    def test_oa_nc_upstream_credentials_are_not_emitted(self):
        self.runtime['dns']['nameserver-policy']['oa.ziyondpharma.com'] = [
            'https://user:DO-NOT-EMIT@example.test/dns-query?token=DO-NOT-EMIT']
        checks, summary = m.audit_dns(self.root, self.runtime, POLICY)
        self.assertNotIn('DO-NOT-EMIT', json.dumps([checks, summary]))
        self.assertEqual(summary['company_wifi_dns']['status'], 'ATTENTION')
        self.assertEqual(summary['mail_dns']['status'], 'PASS')

    def test_company_dns_replaced_by_public_and_fake_ip_exclusion_missing_fail(self):
        dns = self.runtime['dns']
        dns['nameserver-policy']['+.' + POLICY['dns']['company_domain']] = dns['nameserver']
        dns['fake-ip-filter'] = []
        states, _ = self.statuses()
        self.assertEqual(states['dns_company_upstreams'], 'FAIL')
        self.assertEqual(states['dns_company_fake_ip_exclusion'], 'FAIL')

    def test_direct_resolver_must_follow_company_policy(self):
        self.runtime['dns']['direct-nameserver'] = self.runtime['dns']['nameserver']
        states, _ = self.statuses()
        self.assertEqual(states['dns_company_policy_priority'], 'FAIL')
        self.runtime['dns']['direct-nameserver-follow-policy'] = True
        states, _ = self.statuses()
        self.assertEqual(states['dns_company_policy_priority'], 'PASS')

    def test_other_domain_policy_cannot_silently_use_domestic_dns(self):
        self.runtime['dns']['nameserver-policy']['+.example.com'] = ['223.5.5.5']
        states, _ = self.statuses()
        self.assertEqual(states['dns_other_public_paths'], 'FAIL')

    def test_feishu_exception_is_limited_to_exact_policy_keys(self):
        for key in ('+.com', 'geosite:cn', '+.claude.ai', '+.anthropic.com',
                    '+.feishu.cn.example.com', 'feishu.cn'):
            with self.subTest(key=key):
                self.runtime['dns']['nameserver-policy'][key] = ['https://dns.alidns.com/dns-query']
                states, _ = self.statuses()
                self.assertEqual(states['dns_other_public_paths'], 'FAIL')
                del self.runtime['dns']['nameserver-policy'][key]

    def test_feishu_missing_or_changed_resolver_is_detected(self):
        overrides = [None, [], 'system', ['223.5.5.5'],
                     ['http://dns.alidns.com/dns-query'], ['https://example.com/dns-query'],
                     ['https://dns.alidns.com/dns-query', 'system'],
                     ['https://dns.alidns.com/dns-query#DIRECT']]
        for key in POLICY['dns']['feishu_nameserver_policy']:
            original = self.runtime['dns']['nameserver-policy'][key]
            for value in overrides:
                with self.subTest(key=key, value=value):
                    if value is None:
                        self.runtime['dns']['nameserver-policy'].pop(key)
                    else:
                        self.runtime['dns']['nameserver-policy'][key] = value
                    states, summary = self.statuses()
                    self.assertEqual(states['dns_feishu_upstreams'], 'FAIL')
                    self.assertEqual(summary['configuration_status'], 'ATTENTION')
                    self.assertEqual(summary['feishu_exception']['status'], 'ATTENTION')
                    self.runtime['dns']['nameserver-policy'][key] = original

    def test_feishu_resolver_is_not_exempt_in_primary_fallback_or_direct_fields(self):
        for field in ('nameserver', 'fallback', 'direct-nameserver'):
            with self.subTest(field=field):
                saved = copy.deepcopy(self.runtime)
                self.runtime['dns'][field] = ['https://dns.alidns.com/dns-query']
                states, _ = self.statuses()
                item = 'dns_public_encrypted_fixed_route' if field == 'nameserver' else 'dns_other_public_paths'
                self.assertEqual(states[item], 'FAIL')
                self.runtime = saved

    def test_feishu_exemption_does_not_weaken_fixed_public_dns(self):
        self.runtime['dns']['nameserver'] = ['https://1.1.1.1/dns-query#DIRECT']
        states, _ = self.statuses()
        self.assertEqual(states['dns_feishu_upstreams'], 'PASS')
        self.assertEqual(states['dns_public_encrypted_fixed_route'], 'FAIL')
        self.assertEqual(states['dns_public_baseline'], 'FAIL')

    def test_stale_feishu_source_is_reported_without_executing_it(self):
        source_before = self.source.read_text()
        self.source.write_text(source_before.replace('https://dns.alidns.com/dns-query', 'system'))
        with patch.object(m.socket, 'socket') as network, patch.object(m.subprocess, 'run') as command:
            states, _ = self.statuses()
        self.assertEqual(states['dns_feishu_upstreams'], 'PASS')
        self.assertEqual(states['dns_feishu_persistent_source'], 'FAIL')
        network.assert_not_called()
        command.assert_not_called()

    def test_unknown_feishu_source_is_unverified_even_when_public_literal_is_valid(self):
        self.source.write_text('function main(config) { config.dns.nameserver = '
                               + json.dumps(POLICY['dns']['public_nameservers'])
                               + '; config.dns["nameserver-policy"] = buildPolicies(); return config; }')
        states, summary = self.statuses()
        self.assertEqual(states['dns_persistent_source'], 'PASS')
        self.assertEqual(states['dns_feishu_persistent_source'], 'UNVERIFIED')
        self.assertEqual(summary['configuration_status'], 'ATTENTION')

    def test_feishu_upstream_credentials_are_not_emitted(self):
        self.runtime['dns']['nameserver-policy']['+.feishu.cn'] = [
            'https://user:DO-NOT-EMIT@example.test/dns-query?token=DO-NOT-EMIT']
        checks, summary = m.audit_dns(self.root, self.runtime, POLICY)
        self.assertNotIn('DO-NOT-EMIT', json.dumps([checks, summary]))
        self.assertEqual(summary['feishu_exception']['status'], 'ATTENTION')

    def test_dns_report_does_not_echo_credentials_or_tokens_in_upstream_urls(self):
        self.runtime['dns']['nameserver'] = ['https://user:DO-NOT-EMIT@example.test/dns-query?token=DO-NOT-EMIT#DIRECT']
        checks, summary = m.audit_dns(self.root, self.runtime, POLICY)
        self.assertNotIn('DO-NOT-EMIT', json.dumps([checks, summary]))
        self.assertEqual(summary['configuration_status'], 'ATTENTION')

    def test_unknown_persistent_script_is_not_executed_or_assumed_correct(self):
        self.source.write_text('throw new Error("must never execute");')
        states, _ = self.statuses()
        self.assertEqual(states['dns_persistent_source'], 'UNVERIFIED')

    def test_live_company_route_override_is_detected(self):
        live = {'rules': {'rules': [{'type': 'DomainSuffix',
                                     'payload': POLICY['dns']['company_domain'], 'proxy': 'PROXY'}]}}
        checks, _ = m.audit_dns(self.root, self.runtime, POLICY, live)
        states = {x['item']: x['status'] for x in checks}
        self.assertEqual(states['dns_company_live_direct_rules'], 'FAIL')


class LocalObservationTests(unittest.TestCase):
    def command(self, args):
        result = {'status': 'OK', 'stdout': '', 'stderr': ''}
        if args[:2] == ['/usr/bin/defaults', 'read']:
            if args[-1] == 'AppleLocale':
                result['stdout'] = 'en_US\n'
            elif args[2] == '-g':
                result['stdout'] = '(\n "en-US",\n "zh-Hans-US"\n)\n'
            else:
                result.update(status='UNVERIFIED', stderr='The domain/default pair does not exist')
        elif args == ['/sbin/ifconfig', '-a']:
            result['stdout'] = ('lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384\n'
                                '\tinet6 ::1 prefixlen 128\n'
                                'en0: flags=8863<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500\n'
                                '\tinet6 fe80::1234%en0 prefixlen 64\n'
                                '\tinet6 2606:4700::1234 prefixlen 64\n'
                                '\tinet6 fd01::1 prefixlen 64\n'
                                '\tether DO-NOT-EMIT\n')
        elif args == ['/usr/sbin/networksetup', '-listnetworkserviceorder']:
            result['stdout'] = '(1) Wi-Fi\n(Hardware Port: Wi-Fi, Device: en0)\n'
        elif args == ['/usr/sbin/networksetup', '-getinfo', 'Wi-Fi']:
            result['stdout'] = 'IPv6: Off\nWi-Fi ID: DO-NOT-EMIT\n'
        elif args == ['/sbin/route', '-n', 'get', 'default']:
            result['stdout'] = 'interface: en0\ngateway: DO-NOT-EMIT\n'
        elif args == ['/sbin/route', '-n', 'get', '-inet6', 'default']:
            result['stdout'] = 'route: writing to routing socket: not in table\n'
        else:
            self.fail('Unexpected local observation command')
        return result

    def test_local_observations_are_separate_and_do_not_probe_network(self):
        with patch.object(m, 'local_command', side_effect=self.command), patch.object(m.socket, 'socket') as network:
            result = m.observe_local_environment({'ipv6': False, 'dns': {'ipv6': True}}, {'configs': {}})
        self.assertEqual(result['language']['system_languages']['value'], ['en-US', 'zh-Hans-US'])
        self.assertEqual(result['language']['claude_languages']['status'], 'NOT_SET')
        self.assertEqual(result['language']['browser_intl_status'], 'NOT_RUN')
        ipv6 = result['ipv6']
        self.assertEqual(ipv6['interfaces'][0]['ipv6_address_counts']['global'], 1)
        self.assertEqual(ipv6['interfaces'][0]['ipv6_address_counts']['unique_local'], 1)
        self.assertEqual(ipv6['interfaces'][1]['ipv6_address_counts']['loopback'], 1)
        self.assertEqual(ipv6['ipv6_default_route']['status'], 'ABSENT')
        self.assertEqual(ipv6['active_service_modes'][0]['configured_mode'], 'off')
        self.assertIsNone(ipv6['proxy_settings']['live_ipv6'])
        self.assertEqual(ipv6['actual_ipv6_path_status'], 'NOT_RUN')
        serialized = json.dumps(result)
        for hidden in ('DO-NOT-EMIT', 'fe80::1234', '2606:4700::1234', 'fd01::1'):
            self.assertNotIn(hidden, serialized)
        self.assertNotIn('FAIL', serialized)
        network.assert_not_called()

    def test_failed_commands_and_missing_route_are_not_equivalent(self):
        failed = {'status': 'UNVERIFIED', 'stdout': '', 'stderr': 'DO-NOT-EMIT'}
        with patch.object(m, 'local_command', return_value=failed):
            result = m.observe_local_environment({}, None)
        self.assertEqual(result['ipv6']['interface_status'], 'UNVERIFIED')
        self.assertEqual(result['ipv6']['ipv6_default_route']['status'], 'UNVERIFIED')
        self.assertEqual(result['language']['region']['status'], 'UNVERIFIED')
        self.assertNotIn('DO-NOT-EMIT', json.dumps(result))

    def test_local_command_has_timeout_no_shell_and_sanitizes_failure(self):
        with patch.object(m.subprocess, 'run', side_effect=m.subprocess.TimeoutExpired('read', 4)) as run:
            result = m.local_command(['/sbin/ifconfig', '-a'])
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(result['stdout'], '')
        self.assertEqual(run.call_args.kwargs['timeout'], 4)
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_timezone_uses_seasonal_offset_without_system_changes(self):
        for month, expected in ((1, '-05:00'), (7, '-04:00')):
            class FixedDate(m.datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, month, 15, tzinfo=tz)
            with self.subTest(month=month), patch.object(m.Path, 'resolve', return_value=Path('/var/db/timezone/zoneinfo/America/New_York')), patch.object(m, 'datetime', FixedDate):
                result = m.observe_timezone(Path('/not-a-live-path'))
            self.assertEqual(result['iana'], 'America/New_York')
            self.assertEqual(result['utc_offset'], expected)
        with patch.object(m.Path, 'resolve', side_effect=FileNotFoundError):
            self.assertEqual(m.observe_timezone()['status'], 'UNVERIFIED')


class ReportComparisonTests(unittest.TestCase):
    def report(self):
        return {'report_version': 2, 'profile_uid': 'test-profile', 'configuration_status': 'PASS',
                'report_metadata': {'completed_at_utc': '2026-10-25T11:00:00+00:00', 'baseline_sha256': 'a'*64},
                'configuration_fingerprints': {'generated_config_sha256': 'b'*64, 'rules_extension_sha256': 'c'*64},
                'checks': [{'item': 'dns_company_upstreams', 'status': 'PASS'},
                           {'item': 'persistent_rule', 'status': 'PASS'}, {'item': 'persistent_rule', 'status': 'PASS'}],
                'protected_config_inventory': [{'path': '/test/mcp.json', 'exists': True, 'sha256': 'd'*64}],
                'system_observations': {'language': {'system_languages': {'status': 'OBSERVED', 'value': ['en-US']},
                                                   'region': {'status': 'OBSERVED', 'value': 'en_US'},
                                                   'claude_languages': {'status': 'NOT_SET', 'value': None}},
                                        'timezone': {'iana': 'America/New_York', 'utc_offset': '-04:00'},
                                        'ipv6': {'interface_status': 'OBSERVED', 'interfaces': [], 'active_service_modes': [],
                                                 'service_inventory_status': 'OK', 'ipv4_default_route': {'status': 'PRESENT', 'interface': 'en0'},
                                                 'ipv6_default_route': {'status': 'ABSENT', 'interface': None}, 'proxy_settings': {}}}}

    def test_timestamp_alone_is_not_drift_and_old_probes_are_never_reused(self):
        old, current = self.report(), self.report()
        old['report_metadata']['completed_at_utc'] = '2026-10-24T11:00:00+00:00'
        old['actual_exit_tests'] = 'DO-NOT-EMIT: historical result'
        result = m.compare_reports(old, current)
        self.assertEqual(result['comparability'], 'FULL')
        self.assertEqual(result['changed_sections'], [])
        self.assertEqual(result['check_status_changes'], [])
        self.assertEqual(result['actual_exit_comparison_status'], 'NOT_RUN')
        self.assertNotIn('DO-NOT-EMIT', json.dumps(result))

    def test_known_drift_check_regression_and_mcp_change_are_reported(self):
        old, current = self.report(), self.report()
        current['system_observations']['language']['system_languages']['value'] = ['zh-CN', 'en-US']
        current['checks'][2]['status'] = 'FAIL'
        current['protected_config_inventory'][0]['sha256'] = 'e'*64
        result = m.compare_reports(old, current)
        self.assertIn('system_observations.language.system_languages', result['changed_sections'])
        self.assertEqual(result['check_status_changes'][0]['current_status_counts'], {'PASS': 1, 'FAIL': 1})
        self.assertEqual(result['protected_config_changes'], ['/test/mcp.json'])
        self.assertEqual(current['configuration_status'], 'PASS')

    def test_legacy_missing_data_and_different_baseline_are_partial(self):
        current = self.report()
        old = {'checks': [], 'private_data': 'DO-NOT-EMIT', 'report_metadata': {'completed_at_utc': 'DO-NOT-EMIT'}}
        result = m.compare_reports(old, current)
        self.assertEqual(result['comparability'], 'PARTIAL')
        self.assertTrue(result['unavailable_sections'])
        self.assertIsNone(result['previous_completed_at_utc'])
        self.assertNotIn('DO-NOT-EMIT', json.dumps(result))
        old = self.report()
        old['report_metadata']['baseline_sha256'] = 'f'*64
        self.assertEqual(m.compare_reports(old, current)['comparability'], 'PARTIAL')
        old['report_version'] = 999
        self.assertEqual(m.compare_reports(old, current)['status'], 'UNSUPPORTED_VERSION')
        with self.assertRaises(RuntimeError):
            m.compare_reports({'not_an_audit': True}, current)

    def test_metadata_and_observations_do_not_change_business_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('clash-verge.yaml', 'rules.yaml', 'baseline.json'):
                (root/name).write_text('{}')
            ctx = (root, 'profile', root/'rules.yaml', {}, {})
            business = {'configuration_status': 'PASS', 'checks': [{'item': 'company_and_feishu', 'status': 'PASS'}]}
            with patch.object(m, 'audit', return_value=copy.deepcopy(business)), patch.object(m, 'observe_local_environment', return_value={'ipv6': {'interface_status': 'UNVERIFIED'}}):
                result = m.build_audit_report(ctx, {}, None, root/'baseline.json', '2026-10-25T10:00:00+00:00')
            self.assertEqual(result['checks'], business['checks'])
            self.assertEqual(result['configuration_status'], 'PASS')
            self.assertEqual(result['report_version'], 2)
            self.assertEqual(result['report_comparison']['status'], 'NOT_REQUESTED')
            self.assertEqual(result['report_metadata']['external_probes'], 'NOT_RUN')

    def test_default_cli_does_not_write_history_or_run_repair(self):
        report = self.report()
        with patch.object(m.sys, 'argv', ['check_claude.py']), patch.object(m, 'context', return_value=(Path('/test'), '', Path('/test'), {}, {})), patch.object(m, 'live_state', return_value=None), patch.object(m, 'build_audit_report', return_value=report), patch.object(m, 'json_write') as write, patch.object(m, 'repair') as repair, contextlib.redirect_stdout(io.StringIO()):
            code = m.main()
        self.assertEqual(code, 0)
        write.assert_not_called()
        repair.assert_not_called()

    def test_compare_cannot_be_combined_with_mutation_or_overwrite_input(self):
        for arguments in (['repair', '--compare', '/test/old.json'],
                          ['audit', '--compare', '/test/same.json', '--output', '/test/same.json']):
            with self.subTest(arguments=arguments), patch.object(m.sys, 'argv', ['check_claude.py'] + arguments), patch.object(m, 'context') as read, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                m.main()
            read.assert_not_called()

    def test_explicit_compare_cli_reads_old_report_without_copying_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory)/'previous.json'
            old = self.report()
            old['private_data'] = 'DO-NOT-EMIT'
            previous.write_text(json.dumps(old))
            before = previous.read_bytes()
            with patch.object(m.sys, 'argv', ['check_claude.py', 'audit', '--compare', str(previous)]), patch.object(m, 'context', return_value=(Path('/test'), '', Path('/test'), {}, {})), patch.object(m, 'live_state', return_value=None), patch.object(m, 'build_audit_report', return_value=self.report()), patch.object(m, 'json_write') as write, contextlib.redirect_stdout(io.StringIO()) as output:
                code = m.main()
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result['report_comparison']['status'], 'COMPARED')
            self.assertEqual(result['report_comparison']['comparability'], 'FULL')
            self.assertNotIn('DO-NOT-EMIT', output.getvalue())
            self.assertEqual(previous.read_bytes(), before)
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
