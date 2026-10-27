#!/usr/bin/env python3
"""Read-only local network/DNS audit by default; explicit persistent-rule repair."""
import argparse
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import yaml
except ImportError:
    print(json.dumps({"error": "PyYAML unavailable; use an existing Python with PyYAML"}))
    sys.exit(1)

SKILL = Path(__file__).resolve().parents[1]
REPORT_VERSION = 2
DETECTOR_VERSION = '2026-10-25.1'


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def local_command(arguments):
    """Only callers below supply local read commands; never expose raw errors."""
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=4,
                                env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'})
        return {'status': 'OK' if result.returncode == 0 else 'UNVERIFIED',
                'stdout': result.stdout, 'stderr': result.stderr}
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'UNVERIFIED', 'stdout': '', 'stderr': ''}


def language_preference(domain, key, array=False):
    result = local_command(['/usr/bin/defaults', 'read', domain, key])
    text = result['stdout'].strip()
    value = None
    if result['status'] == 'OK':
        if array and text.startswith('(') and text.endswith(')'):
            values = [x.strip().strip('"') for x in text[1:-1].split(',') if x.strip()]
            if values and all(re.fullmatch(r'[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{2,8})*', x) for x in values):
                value = values
        elif not array and re.fullmatch(r'[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{2,8})*(?:@[A-Za-z0-9_=;-]+)?', text):
            value = text
    missing = result['status'] != 'OK' and 'does not exist' in result['stderr']
    return {'status': 'OBSERVED' if value is not None else 'NOT_SET' if missing else 'UNVERIFIED', 'value': value}


def observe_timezone(localtime=Path('/etc/localtime')):
    report = {'status': 'UNVERIFIED', 'iana': None, 'utc_offset': None}
    try:
        resolved = str(localtime.resolve(strict=True))
        if '/zoneinfo/' not in resolved:
            return report
        name = resolved.split('/zoneinfo/', 1)[1]
        offset = datetime.now(ZoneInfo(name)).strftime('%z')
        report.update(status='OBSERVED', iana=name, utc_offset=offset[:3] + ':' + offset[3:])
    except (OSError, RuntimeError, ValueError, ZoneInfoNotFoundError):
        pass
    return report


def parse_interfaces(text):
    interfaces, current = [], None
    for line in text.splitlines():
        match = re.match(r'^([A-Za-z0-9_.:-]+): flags=.*<([^>]+)>', line)
        if match:
            flags = match[2].split(',')
            current = {'interface': match[1], 'up': 'UP' in flags, 'running': 'RUNNING' in flags,
                       'loopback': 'LOOPBACK' in flags,
                       'ipv6_address_counts': dict.fromkeys(('global', 'link_local', 'unique_local', 'loopback', 'other'), 0)}
            interfaces.append(current)
        elif current:
            address = re.match(r'\s+inet6\s+(\S+)', line)
            if address:
                try:
                    ip = ipaddress.IPv6Address(address[1].split('%', 1)[0])
                except ValueError:
                    continue
                scope = ('loopback' if ip.is_loopback else 'link_local' if ip.is_link_local else
                         'unique_local' if ip in ipaddress.IPv6Network('fc00::/7') else
                         'global' if ip.is_global else 'other')
                current['ipv6_address_counts'][scope] += 1
    return sorted(interfaces, key=lambda item: item['interface'])


def observe_default_route(ipv6=False):
    arguments = ['/sbin/route', '-n', 'get'] + (['-inet6'] if ipv6 else []) + ['default']
    result = local_command(arguments)
    match = re.search(r'^\s*interface:\s*([A-Za-z0-9_.:-]+)\s*$', result['stdout'], re.M)
    if result['status'] == 'OK' and match:
        return {'status': 'PRESENT', 'interface': match[1]}
    # macOS route may return zero even when the route is absent.
    absent = any(reason in (result['stdout'] + result['stderr']).lower()
                 for reason in ('not in table', 'not found', 'no route to host'))
    return {'status': 'ABSENT' if absent else 'UNVERIFIED', 'interface': None}


def observe_local_environment(runtime, live):
    language = {
        'system_languages': language_preference('-g', 'AppleLanguages', array=True),
        'region': language_preference('-g', 'AppleLocale'),
        'claude_languages': language_preference('com.anthropic.claudefordesktop', 'AppleLanguages', array=True),
        'browser_intl_status': 'NOT_RUN',
        'effective_claude_language_status': 'UNVERIFIED',
    }
    raw = local_command(['/sbin/ifconfig', '-a'])
    interfaces = parse_interfaces(raw['stdout']) if raw['status'] == 'OK' else []
    active = {item['interface'] for item in interfaces if item['up'] and not item['loopback']}
    services = local_command(['/usr/sbin/networksetup', '-listnetworkserviceorder'])
    modes, service = [], None
    if services['status'] == 'OK':
        for line in services['stdout'].splitlines():
            name = re.match(r'^\(\d+\) (.+)$', line)
            if name:
                service = name[1]
            device = re.search(r'Device: ([A-Za-z0-9_.:-]+)\)', line)
            if device and service:
                if device[1] in active:
                    info = local_command(['/usr/sbin/networksetup', '-getinfo', service])
                    match = re.search(r'^IPv6:\s*(Off|Automatic|Manual|Link-local only)\s*$', info['stdout'], re.M | re.I)
                    modes.append({'interface': device[1], 'status': 'OBSERVED' if info['status'] == 'OK' and match else 'UNVERIFIED',
                                  'configured_mode': match[1].lower() if info['status'] == 'OK' and match else None})
                service = None
    def flag(mapping, key):
        value = mapping.get(key)
        return value if isinstance(value, bool) else None
    return {
        'scope': 'LOCAL_READ_ONLY', 'external_probe_status': 'NOT_RUN',
        'language': language, 'timezone': observe_timezone(),
        'ipv6': {
            'interface_status': 'OBSERVED' if interfaces else 'UNVERIFIED',
            'interfaces': interfaces, 'active_service_modes': sorted(modes, key=lambda item: item['interface']),
            'service_inventory_status': services['status'],
            'ipv4_default_route': observe_default_route(), 'ipv6_default_route': observe_default_route(True),
            'proxy_settings': {'generated_ipv6': flag(runtime, 'ipv6'),
                               'generated_dns_ipv6': flag(runtime.get('dns') or {}, 'ipv6'),
                               'live_ipv6': flag((live or {}).get('configs') or {}, 'ipv6')},
            'actual_ipv6_path_status': 'NOT_RUN',
        },
    }


def compare_reports(previous, current):
    if not isinstance(previous, dict) or 'checks' not in previous or not isinstance(previous['checks'], list):
        raise RuntimeError('Comparison input must be an audit report; no configuration was changed')
    version = previous.get('report_version')
    if version not in (None, REPORT_VERSION):
        return {'status': 'UNSUPPORTED_VERSION', 'actual_exit_comparison_status': 'NOT_RUN'}
    changes, unavailable = [], []
    paths = [('configuration_status',), ('configuration_fingerprints',),
             ('system_observations', 'language', 'system_languages'),
             ('system_observations', 'language', 'region'),
             ('system_observations', 'language', 'claude_languages'),
             ('system_observations', 'timezone', 'iana'),
             ('system_observations', 'timezone', 'utc_offset'),
             ('system_observations', 'ipv6', 'interface_status'),
             ('system_observations', 'ipv6', 'interfaces'),
             ('system_observations', 'ipv6', 'active_service_modes'),
             ('system_observations', 'ipv6', 'service_inventory_status'),
             ('system_observations', 'ipv6', 'ipv4_default_route'),
             ('system_observations', 'ipv6', 'ipv6_default_route'),
             ('system_observations', 'ipv6', 'proxy_settings')]
    def lookup(report, path):
        for part in path:
            if not isinstance(report, dict) or part not in report:
                return False, None
            report = report[part]
        return True, report
    for path in paths:
        old_exists, old = lookup(previous, path)
        new_exists, new = lookup(current, path)
        if not old_exists or not new_exists:
            unavailable.append('.'.join(path))
        elif old != new:
            # Only emit known field names, never arbitrary values from an old report.
            changes.append('.'.join(path))
    states = {'PASS', 'FAIL', 'UNVERIFIED', 'ATTENTION', 'EXEMPT'}
    def check_states(report, name):
        return dict(Counter(item.get('status') if item.get('status') in states else 'UNVERIFIED'
                            for item in report.get('checks', []) if isinstance(item, dict) and item.get('item') == name))
    check_changes = []
    for name in sorted({item['item'] for item in current['checks'] if isinstance(item, dict) and isinstance(item.get('item'), str)}):
        old, new = check_states(previous, name), check_states(current, name)
        if old != new:
            check_changes.append({'item': name, 'previous_status_counts': old, 'current_status_counts': new})
    protected_changes = []
    old_inventory = previous.get('protected_config_inventory', [])
    if not isinstance(old_inventory, list):
        old_inventory = []
    for item in current.get('protected_config_inventory', []):
        old = next((x for x in old_inventory if isinstance(x, dict) and x.get('path') == item['path']), None)
        if old is not None and (old.get('exists'), old.get('sha256')) != (item['exists'], item['sha256']):
            protected_changes.append(item['path'])
    def report_time(report):
        value = (report.get('report_metadata') or {}).get('completed_at_utc')
        try:
            return datetime.fromisoformat(value).isoformat() if isinstance(value, str) else None
        except ValueError:
            return None
    same_profile = previous.get('profile_uid') == current.get('profile_uid') if 'profile_uid' in previous else None
    old_baseline = (previous.get('report_metadata') or {}).get('baseline_sha256')
    same_baseline = old_baseline == current['report_metadata']['baseline_sha256'] if old_baseline else None
    return {'status': 'COMPARED', 'previous_completed_at_utc': report_time(previous),
            'current_completed_at_utc': report_time(current),
            'comparability': 'FULL' if version == REPORT_VERSION and same_profile is True and same_baseline is True and not unavailable else 'PARTIAL',
            'same_profile': same_profile, 'same_baseline': same_baseline,
            'changed_sections': changes, 'unavailable_sections': unavailable,
            'check_status_changes': check_changes, 'protected_config_changes': protected_changes,
            'actual_exit_comparison_status': 'NOT_RUN',
            'interpretation': 'Point-in-time differences only; no automatic repair or account-risk verdict. No old probe result is reused.'}


def build_audit_report(ctx, policy, live, baseline_path, started_at):
    report = audit(ctx, policy, live)
    report['report_version'] = REPORT_VERSION
    report['system_observations'] = observe_local_environment(ctx[4], live)
    report['configuration_fingerprints'] = {
        'generated_config_sha256': digest((ctx[0]/'clash-verge.yaml').read_bytes()),
        'rules_extension_sha256': digest(ctx[2].read_bytes()),
    }
    report['report_metadata'] = {'started_at_utc': started_at, 'completed_at_utc': utc_now(),
                                 'detector_version': DETECTOR_VERSION,
                                 'detector_sha256': digest(Path(__file__).read_bytes()),
                                 'baseline_sha256': digest(baseline_path.read_bytes()),
                                 'scope': 'LOCAL_FILES_LOCAL_API_AND_READ_COMMANDS', 'external_probes': 'NOT_RUN'}
    report['report_comparison'] = {'status': 'NOT_REQUESTED'}
    return report


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_yaml(path):
    value = yaml.safe_load(path.read_text())
    return value if value is not None else {}


def private_write(path, data):
    """Atomic replacement within the same directory; no secret in diagnostics."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.claude-network-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_write(path, value):
    private_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def split_rule(text):
    parts, start, depth = [], 0, 0
    for index, char in enumerate(text):
        depth += (char == '(') - (char == ')')
        if char == ',' and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def matches(text, host, process):
    parts = split_rule(text)
    kind = parts[0].upper()
    value = parts[1] if len(parts) > 1 else ''
    if kind == 'DOMAIN':
        return host.lower() == value.lower()
    if kind == 'DOMAIN-SUFFIX':
        return host.lower() == value.lower() or host.lower().endswith('.' + value.lower())
    if kind == 'DOMAIN-KEYWORD':
        return value.lower() in host.lower()
    if kind == 'PROCESS-NAME':
        return process == value
    if kind in ('AND', 'OR', 'NOT'):
        expressions = split_rule(value[1:-1])
        results = [matches(x[1:-1], host, process) for x in expressions]
        if kind == 'AND':
            return False if False in results else (None if None in results else True)
        if kind == 'OR':
            return True if True in results else (None if None in results else False)
        return None if not results or results[0] is None else not results[0]
    if kind in ('MATCH', 'FINAL'):
        return True
    # GeoIP, CIDR, rule sets, ports and process paths need actual connection metadata.
    return None


def first_target(rules, host, process='', domain_only=False):
    for rule in rules:
        result = matches(rule, host, process)
        if result is None:
            if domain_only:
                continue
            return None
        if result:
            parts = split_rule(rule)
            return parts[1] if parts[0].upper() in ('MATCH', 'FINAL') else parts[2]
    return None


def requirements(policy):
    fixed = policy['fixed_proxy']
    intercom = ('AND,((PROCESS-NAME,' + policy['intercom_process'] + '),(DOMAIN,'
                + policy['intercom_host'] + ')),' + fixed)
    return ['DOMAIN,' + policy['stun_hosts'][0] + ',' + fixed, intercom,
            *['DOMAIN,' + h + ',' + fixed for h in policy['stun_hosts'][1:]]]


def rule_identity(rule):
    return tuple(split_rule(rule)[:2])


def canonical(value):
    return re.sub(r'[^a-z0-9.\-]', '', value.lower())


def auxiliary_rules(policy):
    auxiliary = policy.get('desktop_auxiliary')
    if not auxiliary:
        return []
    process = auxiliary['process_name']
    return [
        'AND,((PROCESS-NAME,' + process + '),(DOMAIN,' + auxiliary['widget_host'] + ')),' + policy['fixed_proxy'],
        'AND,((PROCESS-NAME,' + process + '),(DOMAIN-SUFFIX,' + auxiliary['hcaptcha_suffix'] + ')),' + policy['fixed_proxy'],
    ]


def logical_api_payload(expression):
    return expression.replace('PROCESS-NAME', 'ProcessName').replace(
        'DOMAIN-SUFFIX', 'DomainSuffix').replace('DOMAIN', 'Domain')


def api_rule_strings(rules, policy):
    known = requirements(policy) + auxiliary_rules(policy)
    names = {'Domain':'DOMAIN', 'DomainSuffix':'DOMAIN-SUFFIX',
             'DomainKeyword':'DOMAIN-KEYWORD', 'ProcessName':'PROCESS-NAME', 'Match':'MATCH'}
    output = []
    for item in rules:
        if item.get('extra', {}).get('disabled'):
            continue
        kind, payload, proxy = item.get('type', ''), item.get('payload', ''), item.get('proxy', '')
        if kind == 'Match':
            output.append('MATCH,' + proxy)
        elif kind in names:
            output.append(names[kind] + ',' + payload + ',' + proxy)
        elif kind == 'AND':
            match = next((r for r in known if split_rule(r)[0] == 'AND' and canonical(
                logical_api_payload(split_rule(r)[1])) == canonical(payload)), None)
            output.append(','.join(split_rule(match)[:2]) + ',' + proxy if match else 'UNKNOWN,' + payload + ',' + proxy)
        else:
            output.append('UNKNOWN,' + payload + ',' + proxy)
    return output


def planned_rules(extension, runtime, policy):
    fixed, group = policy['fixed_proxy'], policy['claude_group']
    required = requirements(policy)
    additions = []
    for kind, domains in [('DOMAIN-SUFFIX', policy['domain_suffixes']),
                          ('DOMAIN', policy['exact_domains'])]:
        for host in domains:
            target = first_target(runtime.get('rules', []), host, domain_only=True)
            if target not in (fixed, group):
                additions.append(kind + ',' + host + ',' + group)
    existing = extension.get('prepend', [])
    for key in ('prepend', 'append', 'delete'):
        if not isinstance(extension.get(key, []), list):
            raise ValueError('unsupported rule extension structure')
    need_required = any(r not in existing for r in required)
    for host in policy['stun_hosts']:
        if first_target(existing + runtime.get('rules', []), host) != fixed:
            need_required = True
    if first_target(existing + runtime.get('rules', []), policy['intercom_host'],
                    policy['intercom_process']) != fixed:
        need_required = True
    if not need_required and not additions:
        return extension, []
    promoted = list(dict.fromkeys(required + additions))
    identities = {rule_identity(r) for r in promoted}
    updated = dict(extension)
    updated['prepend'] = promoted + [r for r in existing if rule_identity(r) not in identities]
    return updated, promoted


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=5)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def live_state(root, runtime):
    candidates = [Path('/var/run/clash-verge-service/users') / str(os.getuid()) / 'verge-mihomo.sock']
    if runtime.get('external-controller-unix'):
        candidates.append(Path(runtime['external-controller-unix']))
    for path in candidates:
        if not path.exists():
            continue
        connection = UnixConnection(path)
        try:
            result = {}
            for endpoint in ('configs', 'proxies', 'rules', 'connections'):
                headers = {'Authorization': 'Bearer ' + str(runtime.get('secret', ''))}
                connection.request('GET', '/' + endpoint, headers=headers)
                response = connection.getresponse()
                data = response.read()
                if response.status != 200:
                    raise RuntimeError('local API unavailable')
                result[endpoint] = json.loads(data)
            return result
        except (OSError, ValueError, http.client.HTTPException, RuntimeError):
            pass
        finally:
            connection.close()
    return None


def context(root):
    root = root.expanduser().resolve()
    metadata = read_yaml(root / 'profiles.yaml')
    items = {i['uid']: i for i in metadata.get('items', [])}
    active = items[metadata['current']]
    rule_item = items[active['option']['rules']]
    target = root / 'profiles' / rule_item['file']
    if target.is_symlink() or target.resolve().parent != (root / 'profiles').resolve():
        raise ValueError('unsafe extension path')
    runtime = read_yaml(root / 'clash-verge.yaml')
    return root, metadata['current'], target, read_yaml(target), runtime


def observe_dns_paths(live, policy):
    """Classify existing connection metadata; never infer DNS payloads or resolver brands."""
    summary = {
        'observation_status': 'UNAVAILABLE',
        'actual_comparison_status': 'NOT_RUN',
        'resolver_origin_status': 'UNVERIFIED',
        'connections': [],
        'detail': 'Endpoint/route observations only. HTTPS may be an exit trace rather than DoH; '
                  'a different proxy route may add remote DNS. No matches do not establish absence of leakage.',
    }
    snapshot = live.get('connections') if isinstance(live, dict) else None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('connections'), list):
        return summary
    endpoints = {'1.1.1.1', '1.0.0.1', '8.8.8.8', '8.8.4.4',
                 'cloudflare-dns.com', 'one.one.one.one', 'dns.google'}
    for connection in snapshot['connections']:
        meta = connection.get('metadata') or {}
        host = str(meta.get('host') or '').lower().rstrip('.')
        address = str(meta.get('destinationIP') or '')
        port = str(meta.get('destinationPort') or '')
        transport = str(meta.get('network') or '').lower()
        probe = (host.endswith('.d.ip.net.coffee') and
                 re.fullmatch(r'[a-z0-9-]+\.d\.ip\.net\.coffee', host))
        endpoint = host if host in endpoints else address if address in endpoints else None
        if probe and port == '443' and transport in ('tcp', 'udp'):
            kind, target = 'DNS_TEST_HTTPS', host
        elif endpoint and port in ('443', '853', '53') and transport in ('tcp', 'udp'):
            kind, target = 'RESOLVER_ENDPOINT_PURPOSE_UNVERIFIED', endpoint
        else:
            continue
        chains = connection.get('chains') or []
        route = ('FIXED' if policy['fixed_proxy'] in chains else 'DIRECT' if 'DIRECT' in chains
                 else 'OTHER_PROXY' if chains else 'UNKNOWN')
        process = str(meta.get('process') or '')
        client = ('CHROME' if process.startswith('Google Chrome') else
                  'CLAUDE' if process.startswith('Claude') else 'OTHER' if process else 'UNKNOWN')
        traffic = [connection.get(field, 0) for field in ('upload', 'download')]
        summary['connections'].append({
            'kind': kind, 'endpoint': target, 'port': port, 'transport': transport,
            'route': route, 'client': client,
            'bidirectional': all(isinstance(n, (int, float)) and n > 0 for n in traffic),
        })
    summary['observation_status'] = 'OBSERVED' if summary['connections'] else 'NO_MATCHES_IN_SNAPSHOT'
    return summary


def observe_claude_dns_path(live, policy):
    """Separate current business connection routes from unperformed DNS/TLS probes."""
    summary = {
        'observation_status': 'UNAVAILABLE',
        'dns_path_status': 'UNVERIFIED',
        'actual_test_status': 'NOT_RUN',
        'tls_test_status': 'NOT_RUN',
        'authoritative_comparison_status': 'NOT_RUN',
        'route_counts': {key: 0 for key in ('FIXED', 'DIRECT', 'OTHER_PROXY', 'UNKNOWN')},
        'connections': [],
        'detail': 'Existing Claude connection metadata only; fixed business routes do not prove DNS routing. '
                  'AAAA answers do not prove IPv6 traffic. No snapshot matches do not establish no bypass. '
                  'Non-fixed samples require review, not automatic DNS attribution or repair.',
    }
    snapshot = live.get('connections') if isinstance(live, dict) else None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('connections'), list):
        return summary
    for connection in snapshot['connections']:
        meta = connection.get('metadata') or {}
        host = str(meta.get('host') or '').lower().rstrip('.')
        scope = next((h for h in policy['exact_domains'] if host == h), None)
        if scope is None:
            scope = next((h for h in policy['domain_suffixes']
                          if host == h or host.endswith('.' + h)), None)
        if scope is None:
            continue
        chains = connection.get('chains') or []
        route = ('FIXED' if policy['fixed_proxy'] in chains else 'DIRECT' if 'DIRECT' in chains
                 else 'OTHER_PROXY' if chains else 'UNKNOWN')
        transport = str(meta.get('network') or '').lower()
        traffic = [connection.get(field, 0) for field in ('upload', 'download')]
        summary['connections'].append({
            'host_scope': scope,
            'route': route,
            'transport': transport if transport in ('tcp', 'udp') else 'UNKNOWN',
            'ipv6_destination_observed': ':' in str(meta.get('destinationIP') or ''),
            'bidirectional': all(isinstance(n, (int, float)) and n > 0 for n in traffic),
        })
        summary['route_counts'][route] += 1
    summary['observation_status'] = 'OBSERVED' if summary['connections'] else 'NO_MATCHES_IN_SNAPSHOT'
    return summary


def audit_desktop_auxiliary(extension, runtime, policy, live):
    """Audit two approved process-scoped rules and existing traffic; no active probes."""
    auxiliary = policy.get('desktop_auxiliary')
    if not auxiliary:
        return [], {'configuration_status': 'NOT_CONFIGURED', 'active_test_status': 'NOT_RUN'}
    checks = []
    process, fixed = auxiliary['process_name'], policy['fixed_proxy']
    targets = [('widget', auxiliary['widget_host']), ('hcaptcha', auxiliary['hcaptcha_suffix'])]
    rules = auxiliary_rules(policy)
    normalized = api_rule_strings(live['rules'].get('rules', []), policy) if live else None

    def check(name, ok, detail, unknown=False):
        checks.append({'item': 'desktop_aux_' + name,
                       'status': 'PASS' if ok else ('UNVERIFIED' if unknown else 'FAIL'), 'detail': detail})

    for (label, host), rule in zip(targets, rules):
        check('persistent:' + label, rule in extension.get('prepend', []), rule)
        value = first_target(runtime.get('rules', []), host, process)
        check('generated_route:' + label, value == fixed, 'First determinable target: ' + str(value), value is None)
        if live:
            payload = canonical(logical_api_payload(split_rule(rule)[1]))
            found = any(r.get('type') == 'AND' and r.get('proxy') == fixed and
                        not r.get('extra', {}).get('disabled') and canonical(r.get('payload', '')) == payload
                        for r in live['rules'].get('rules', []))
            check('live_rule:' + label, found, 'Approved process and domain conjunction must be enabled')
            value = first_target(normalized, host, process)
            check('live_route:' + label, value == fixed, 'First determinable live target: ' + str(value), value is None)
        else:
            check('live_rule:' + label, False, 'Local controller unavailable', True)
    samples = [auxiliary['widget_host'], auxiliary['hcaptcha_suffix'], 'probe.' + auxiliary['hcaptcha_suffix']]
    other_processes = ('', 'Google Chrome Helper', 'ChatGPT', 'Claude Code')
    sources = {'persistent': extension.get('prepend', []) + extension.get('append', []),
               'generated': runtime.get('rules', [])}
    if normalized is not None:
        sources['live'] = normalized
    for source, declarations in sources.items():
        broad = any(split_rule(r)[-1] == fixed and
                    any(matches(r, host, other) is True for host in samples for other in other_processes)
                    for r in declarations)
        check('scope:' + source, not broad,
              'Known matching declarations must not send other processes to the fixed node; unknown rule sets are not inferred')
    snapshot = live.get('connections') if isinstance(live, dict) else None
    available = isinstance(snapshot, dict) and isinstance(snapshot.get('connections'), list)
    report = {'active_test_status': 'NOT_RUN',
              'detail': 'Current metadata only; no reload, help-panel action, CAPTCHA, cache change or network probe. '
                        'Historical widget success never fills current results; missing hCaptcha traffic remains unverified.',
              'targets': {}}
    for label, host in targets:
        rows, other_count = [], 0
        for connection in snapshot['connections'] if available else []:
            meta = connection.get('metadata') or {}
            name = str(meta.get('host') or '').lower().rstrip('.')
            if not (name == host or (label == 'hcaptcha' and name.endswith('.' + host))):
                continue
            if meta.get('process') != process:
                other_count += 1
                continue
            verified = str(meta.get('processPath') or '').startswith(auxiliary['process_path_prefix'])
            traffic = [connection.get(field, 0) for field in ('upload', 'download')]
            row = {'process_identity': 'VERIFIED' if verified else 'UNVERIFIED',
                   'fixed_route': fixed in (connection.get('chains') or []),
                   'bidirectional': all(isinstance(n, (int, float)) and n > 0 for n in traffic)}
            rows.append(row)
            if verified:
                check('observed_route:' + label, row['fixed_route'],
                      'Verified Claude.app process; current connection chain only, not public-IP response')
        bad = any(r['process_identity'] == 'VERIFIED' and not r['fixed_route'] for r in rows)
        proven = bool(rows) and all(r['process_identity'] == 'VERIFIED' and r['fixed_route'] and
                                    r['bidirectional'] for r in rows)
        report['targets'][label] = {
            'host_scope': host,
            'observation_status': ('OBSERVED' if rows else 'NO_MATCHES_IN_SNAPSHOT') if available else 'UNAVAILABLE',
            'actual_traffic_status': 'FAIL' if bad else 'PASS' if proven else 'UNVERIFIED',
            'other_process_sample_count': other_count, 'connections': rows,
        }
    report['configuration_status'] = 'PASS' if all(c['status'] == 'PASS' for c in checks
                                                  if 'observed_route:' not in c['item']) else 'ATTENTION'
    return checks, report


def audit_dns(root, runtime, policy, live=None):
    """Inspect declared DNS paths without executing scripts or sending DNS queries."""
    checks = []

    def check(name, ok, detail, uncertain=False):
        checks.append({'item': name, 'status': 'PASS' if ok else ('UNVERIFIED' if uncertain else 'FAIL'),
                       'detail': detail})

    expected = policy.get('dns')
    if not expected:
        check('dns_baseline', False, 'DNS baseline missing; do not infer or change upstreams', True)
        return checks, {'configuration_status': 'ATTENTION', 'actual_test_status': 'NOT_RUN',
                        'company_access_status': 'NOT_TESTED',
                        'claude_path_observations': observe_claude_dns_path(live, policy)}
    dns = runtime.get('dns') or {}
    fixed = policy['fixed_proxy']

    def resolvers(value):
        if isinstance(value, str):
            return [value]
        return value if isinstance(value, list) and all(isinstance(x, str) for x in value) else []

    def protected_upstream(value):
        try:
            parsed = urlsplit(value)
            return (parsed.scheme == 'https' and bool(parsed.hostname)
                    and not parsed.username and not parsed.password
                    and unquote(parsed.fragment.split('&', 1)[0]) == fixed)
        except ValueError:
            return False

    public = resolvers(dns.get('nameserver'))
    check('dns_enabled', dns.get('enable') is True, 'Generated DNS must be enabled')
    check('dns_public_encrypted_fixed_route', bool(public) and all(map(protected_upstream, public)),
          'Every ordinary upstream must use HTTPS and explicitly select the fixed proxy')
    check('dns_public_baseline', set(public) == set(expected['public_nameservers']),
          'Compare approved upstreams; a deviation is not proof of observed leakage')
    overrides = []
    for field in ('fallback', 'direct-nameserver'):
        value = dns.get(field)
        if value not in (None, [], ''):
            entries = resolvers(value)
            overrides.append(bool(entries) and all(map(protected_upstream, entries)))
    policies = dns.get('nameserver-policy') or {}
    company_key = '+.' + expected['company_domain']
    company_public_policies = expected.get('company_public_nameserver_policy', {})
    company_wifi_policies = expected.get('company_wifi_nameserver_policy', {})
    feishu_policies = expected.get('feishu_nameserver_policy', {})
    mail_wifi_hosts = [h for h in expected.get('company_unpinned_hosts', []) if h in company_wifi_policies]

    def approved_company_public_upstream(key, value):
        entries = resolvers(value)
        return (key in company_public_policies and bool(entries)
                and set(entries) == set(company_public_policies[key])
                and all(map(protected_upstream, entries)))

    def approved_feishu_upstream(key, value):
        entries = resolvers(value)
        return (key in feishu_policies and bool(entries)
                and set(entries) == set(feishu_policies[key]))

    def approved_company_wifi_upstream(key, value):
        entries = resolvers(value)
        return (key in company_wifi_policies and bool(entries)
                and set(entries) == set(company_wifi_policies[key]))

    for key, value in policies.items():
        if (key != company_key and not approved_feishu_upstream(key, value)
                and not approved_company_wifi_upstream(key, value)):
            entries = resolvers(value)
            overrides.append(bool(entries) and all(map(protected_upstream, entries)))
    check('dns_other_public_paths', all(overrides),
          'Only approved company, exact Wi-Fi DHCP and Feishu policies may bypass the protected public path; fallback/direct remain checked')
    company_wifi_ok = all(approved_company_wifi_upstream(key, policies.get(key))
                          for key in company_wifi_policies)
    if company_wifi_policies:
        check('dns_company_wifi_upstreams', company_wifi_ok,
              'Exact OA/NC/mail hosts retain only their approved Wi-Fi DHCP resolver; current answers are not queried')
        check('dns_company_wifi_unpinned_hosts', all(
            h not in (runtime.get('hosts') or {}) for h in company_wifi_policies),
            'OA/NC/mail must follow Wi-Fi DNS rather than static private or public host mappings')
    if mail_wifi_hosts:
        check('dns_mail_wifi_upstreams', all(
            approved_company_wifi_upstream(h, policies.get(h)) for h in mail_wifi_hosts),
            'Exact mail DNS follows approved Wi-Fi DHCP; this is not a connection or account test')
    feishu_ok = all(approved_feishu_upstream(key, policies.get(key)) for key in feishu_policies)
    if feishu_policies:
        check('dns_feishu_upstreams', feishu_ok,
              'Both approved Feishu suffix policies retain only their confirmed encrypted resolver')
    check('dns_company_upstreams', set(resolvers(policies.get(company_key))) == set(expected['company_nameservers']),
          'Company suffix retains its confirmed private DNS exception')
    company_public_ok = all(approved_company_public_upstream(key, policies.get(key))
                            for key in company_public_policies)
    if company_public_policies:
        check('dns_company_public_upstreams', company_public_ok,
              'Approved exact public company hosts retain the Cloudflare HTTPS resolvers through the fixed proxy')
    company_domain = expected['company_domain'].lower()
    other_company_policies = [value for key, value in policies.items()
                              if key != company_key and key not in company_public_policies
                              and key not in company_wifi_policies
                              and (key.lower().lstrip('+*.') == company_domain
                                   or key.lower().endswith('.' + company_domain))]
    check('dns_company_other_policy_scope', all(
        set(resolvers(value)) == set(expected['company_nameservers']) for value in other_company_policies),
        'Public and Wi-Fi company overrides stay limited to approved exact hosts; other company policies retain private DNS')
    check('dns_company_policy_priority', not dns.get('direct-nameserver') or dns.get('direct-nameserver-follow-policy') is True,
          'A separate direct resolver must still honor company nameserver-policy')
    check('dns_company_fake_ip_exclusion', company_key in resolvers(dns.get('fake-ip-filter'))
          and dns.get('fake-ip-filter-mode', 'blacklist') == 'blacklist',
          'Company suffix must remain excluded from fake IP answers')
    check('dns_company_hosts', all((runtime.get('hosts') or {}).get(h) == ip
                                  for h, ip in expected['company_hosts'].items()),
          'Preserve confirmed company host mappings')
    unpinned = expected.get('company_unpinned_hosts', [])
    unpinned_ok = all(h not in (runtime.get('hosts') or {}) for h in unpinned)
    if unpinned:
        check('dns_company_unpinned_hosts', unpinned_ok,
              'Approved unpinned company hosts must use DNS rather than a static private or public IP mapping')
    check('dns_company_use_hosts', dns.get('use-hosts') is True, 'Company host mappings must remain enabled')
    rules = runtime.get('rules', [])
    company_hosts = [expected['company_domain'], *expected['company_hosts'], *expected['company_test_hosts']]
    targets = [first_target(rules, h) for h in company_hosts]
    check('dns_company_direct_rules', all(t == 'DIRECT' for t in targets),
          'First determinable company routes remain DIRECT',
          all(t in ('DIRECT', None) for t in targets) and any(t is None for t in targets))
    if live is not None:
        live_rules = api_rule_strings(live['rules'].get('rules', []), policy)
        targets = [first_target(live_rules, h) for h in company_hosts]
        check('dns_company_live_direct_rules', all(t == 'DIRECT' for t in targets),
              'Live company rules remain DIRECT; this does not establish intranet reachability',
              all(t in ('DIRECT', None) for t in targets) and any(t is None for t in targets))
    check('dns_tun_hijack', 'any:53' in resolvers((runtime.get('tun') or {}).get('dns-hijack')),
          'Preserve existing TUN interception of ordinary port-53 DNS')

    relative = Path(expected['persistent_script'])
    source = root / relative
    source_hash = None
    source_text = None
    if (relative.is_absolute() or '..' in relative.parts or source.is_symlink()
            or source.resolve().parent != (root/'profiles').resolve()):
        check('dns_persistent_source', False, 'Unsafe persistent source path; not read')
    elif not source.is_file():
        check('dns_persistent_source', False, 'Persistent DNS script missing; inspect generation sources', True)
    else:
        data = source.read_bytes()
        source_hash = digest(data)
        source_text = data.decode()
        assignments = re.findall(r'config\.dns\.nameserver\s*=\s*(\[[\s\S]*?\])\s*;', source_text)
        try:
            declared = json.loads(assignments[0]) if len(assignments) == 1 else None
        except ValueError:
            declared = None
        check('dns_persistent_source', declared is not None and
              set(resolvers(declared)) == set(expected['public_nameservers']),
              'Inspect the known literal assignment only; never execute user configuration scripts',
              declared is None)
    if feishu_policies:
        declarations = {}
        for key in feishu_policies:
            matches = re.findall(re.escape(json.dumps(key)) + r'\s*:\s*(\[[\s\S]*?\])', source_text or '')
            try:
                declarations[key] = json.loads(matches[0]) if len(matches) == 1 else None
            except ValueError:
                declarations[key] = None
        source_known = all(value is not None for value in declarations.values())
        check('dns_feishu_persistent_source', source_known and all(
            approved_feishu_upstream(key, value) for key, value in declarations.items()),
            'Inspect known Feishu literal declarations only; generated configuration and actual use are separate evidence',
            not source_known)
    if company_public_policies:
        declarations = {}
        for key in company_public_policies:
            matches = re.findall(re.escape(json.dumps(key)) + r'\s*:\s*(\[[\s\S]*?\])', source_text or '')
            try:
                declarations[key] = json.loads(matches[0]) if len(matches) == 1 else None
            except ValueError:
                declarations[key] = None
        source_known = all(value is not None for value in declarations.values())
        check('dns_company_public_persistent_source', source_known and all(
            approved_company_public_upstream(key, value) for key, value in declarations.items()),
            'Inspect known exact public company literal declarations only; never execute the persistent script',
            not source_known)
    if company_wifi_policies:
        declarations = {}
        for key in company_wifi_policies:
            matches = re.findall(re.escape(json.dumps(key)) + r'\s*:\s*(\[[\s\S]*?\])', source_text or '')
            try:
                declarations[key] = json.loads(matches[0]) if len(matches) == 1 else None
            except ValueError:
                declarations[key] = None
        source_known = all(value is not None for value in declarations.values())
        check('dns_company_wifi_persistent_source', source_known and all(
            approved_company_wifi_upstream(key, value) for key, value in declarations.items()),
            'Inspect known exact OA/NC/mail DHCP literal declarations only; never execute the persistent script',
            not source_known)
        if mail_wifi_hosts:
            mail_source_known = all(declarations.get(h) is not None for h in mail_wifi_hosts)
            check('dns_mail_wifi_persistent_source', mail_source_known and all(
                approved_company_wifi_upstream(h, declarations[h]) for h in mail_wifi_hosts),
                'Inspect known exact mail DHCP declaration only; never execute the persistent script',
                not mail_source_known)
    if unpinned:
        domain_literals = re.findall(r'\bconst\s+domain\s*=\s*("(?:[^"\\]|\\.)*")\s*;', source_text or '')
        try:
            domains = [json.loads(value) for value in domain_literals]
        except ValueError:
            domains = None
        host_lines = [line.strip() for line in (source_text or '').splitlines() if 'config.hosts' in line]
        known_deletion = (len(unpinned) == 1 and domains == unpinned and host_lines == [
            'config.hosts = { ...(config.hosts || {}) };', 'delete config.hosts[domain];'])
        check('dns_company_unpinned_persistent_source', known_deletion,
              'Inspect the known mail-host deletion declaration only; unknown source structure requires review, never execution',
              not known_deletion)
    summary = {
        'configuration_status': 'PASS' if all(x['status'] == 'PASS' for x in checks) else 'ATTENTION',
        'upstream_evidence': 'Generated YAML and static script declaration; live upstream use needs an actual test',
        'persistent_source_sha256': source_hash,
        'bootstrap_exception': {
            'fields_present': [f for f in expected['bootstrap_exception_fields'] if dns.get(f)],
            'status': 'EXEMPT',
            'detail': 'Domestic bootstrap/node-resolution upstreams are retained; this is not zero domestic DNS traffic'},
        'actual_test_status': 'NOT_RUN',
        'resolver_path_observations': observe_dns_paths(live, policy),
        'claude_path_observations': observe_claude_dns_path(live, policy),
        'company_access_status': 'NOT_TESTED',
        'company_access_note': 'OA/NC/mail use exact Wi-Fi DHCP DNS policies. Current answers, caches, browser access and other private services remain untested',
    }
    if company_public_policies:
        summary['company_public_dns'] = {
            'status': 'PASS' if company_public_ok else 'ATTENTION',
            'policy_domains': sorted(company_public_policies),
            'detail': 'Approved exact public company overrides use the protected public path; OA/NC/mail Wi-Fi DNS is checked separately',
            'actual_test_status': 'NOT_RUN',
        }
    if company_wifi_policies:
        summary['company_wifi_dns'] = {
            'status': 'EXEMPT' if company_wifi_ok else 'ATTENTION',
            'policy_domains': sorted(company_wifi_policies),
            'detail': 'Only exact OA/NC/mail policies may use the approved Wi-Fi DHCP resolver; inspect source, hosts and DIRECT checks separately. Network switching has not been tested by this audit',
            'actual_test_status': 'NOT_RUN',
            'cache_test_status': 'NOT_RUN',
            'browser_test_status': 'NOT_RUN',
            'dhcp_runtime_status': 'NOT_RUN',
            'udp68_conflict_status': 'NOT_RUN',
            'runtime_note': 'Configuration does not prove DHCP resolver health. Cache clearing is global and may affect OA and mail; see the NC DHCP DNS incident record.',
        }
    if mail_wifi_hosts:
        summary['mail_dns'] = {
            'status': 'PASS' if all(approved_company_wifi_upstream(h, policies.get(h))
                                  for h in mail_wifi_hosts) else 'ATTENTION',
            'policy_domains': list(mail_wifi_hosts),
            'detail': 'Exact mail Wi-Fi DHCP policy only; persistent source, hosts, DIRECT and actual connectivity are separate checks',
            'actual_test_status': 'NOT_RUN',
            'cache_test_status': 'NOT_RUN',
            'connection_test_status': 'NOT_RUN',
        }
    if unpinned:
        summary['company_unpinned_hosts'] = {
            'status': 'PASS' if unpinned_ok else 'ATTENTION',
            'policy_domains': list(unpinned),
            'detail': 'Generated exact host mappings are absent; inspect the separate persistent-source check',
            'actual_test_status': 'NOT_RUN',
        }
    if feishu_policies:
        summary['feishu_exception'] = {
            'status': 'EXEMPT' if feishu_ok else 'ATTENTION',
            'policy_domains': sorted(feishu_policies),
            'detail': 'Approved service-specific encrypted DNS; not a blanket domestic-DNS exemption',
            'actual_test_status': 'NOT_RUN',
        }
    return checks, summary


def audit(ctx, policy, live):
    root, uid, target, extension, runtime = ctx
    checks = []

    def check(name, status, detail):
        checks.append({'item': name, 'status': status, 'detail': detail})

    fixed, group = policy['fixed_proxy'], policy['claude_group']
    entities = {p['name']: p for p in runtime.get('proxies', [])}
    groups = {g['name']: g for g in runtime.get('proxy-groups', [])}
    node = entities.get(fixed, {})
    identity_ok = (node.get('type') == 'socks5' and node.get('server') == policy['proxy_server']
                   and node.get('port') == policy['proxy_port'])
    check('fixed_proxy_identity', 'PASS' if identity_ok else 'FAIL',
          'Known SOCKS5 endpoint present' if identity_ok else 'Missing or changed endpoint; do not overwrite credentials')
    check('fixed_proxy_udp', 'PASS' if node.get('udp') is True else 'FAIL', 'UDP must be enabled')
    check('dialer', 'PASS' if node.get('dialer-proxy') == policy['dialer_group'] else 'FAIL',
          'Expected existing dialer group: ' + policy['dialer_group'])
    check('claude_group_membership', 'PASS' if fixed in groups.get(group, {}).get('proxies', []) else 'FAIL',
          'Fixed node must be available in Claude group')
    for rule in requirements(policy):
        check('persistent_rule', 'PASS' if rule in extension.get('prepend', []) else 'FAIL', rule)
    for host, process in [(h, '') for h in policy['stun_hosts']] + [(policy['intercom_host'], policy['intercom_process'])]:
        value = first_target(runtime.get('rules', []), host, process)
        check('generated_route:' + host, 'PASS' if value == fixed else ('UNVERIFIED' if value is None else 'FAIL'),
              'First determinable target: ' + str(value))
    for host in policy['domain_suffixes'] + policy['exact_domains']:
        value = first_target(runtime.get('rules', []), host, domain_only=True)
        check('claude_domain_declaration:' + host, 'PASS' if value in (fixed, group) else 'FAIL',
              'Domain-only comparison (metadata/rule-set precedence needs real traffic): ' + str(value))
    observed = []
    if live is None:
        check('live_api', 'UNVERIFIED', 'Local controller unavailable; generated YAML is not live proof')
    else:
        configs = live['configs']
        check('live_mode', 'PASS' if configs.get('mode') == policy['mode'] else 'FAIL', 'Expected rule mode')
        check('live_tun', 'PASS' if configs.get('tun', {}).get('enable') is True else 'FAIL', 'Expected TUN enabled')
        proxies = live['proxies'].get('proxies', {})
        check('claude_selection', 'PASS' if proxies.get(group, {}).get('now') == fixed else 'FAIL',
              'Claude group must select fixed node')
        # Resolve the dialer selection recursively to detect cycles or missing targets.
        seen, name = {fixed}, node.get('dialer-proxy')
        chain_ok = False
        while name and name not in seen:
            seen.add(name)
            entity = proxies.get(name)
            if not entity:
                break
            if entity.get('now'):
                name = entity['now']
            elif name in entities:
                name = entities[name].get('dialer-proxy')
                if name is None:
                    chain_ok = True
            else:
                break
        check('dialer_chain', 'PASS' if chain_ok else 'FAIL', 'Resolved without missing target or self-cycle')
        api_rules = live['rules'].get('rules', [])
        normalized = api_rule_strings(api_rules, policy)
        for rule in requirements(policy):
            parts = split_rule(rule)
            type_name = 'Domain' if parts[0] == 'DOMAIN' else 'AND'
            payload = parts[1].replace('PROCESS-NAME', 'ProcessName').replace('DOMAIN', 'Domain')
            # Mihomo represents logical rule payloads with && instead of YAML commas.
            found = any(r.get('type') == type_name and r.get('proxy') == fixed and
                        canonical(r.get('payload', '')) == canonical(payload) for r in api_rules)
            check('live_rule', 'PASS' if found else 'FAIL', rule)
        for host, process in [(h, '') for h in policy['stun_hosts']] + [(policy['intercom_host'], policy['intercom_process'])]:
            value = first_target(normalized, host, process)
            check('live_rule_order:' + host, 'PASS' if value == fixed else ('UNVERIFIED' if value is None else 'FAIL'),
                  'First determinable live target: ' + str(value))
        for host in policy['domain_suffixes'] + policy['exact_domains']:
            value = first_target(normalized, host, domain_only=True)
            check('live_domain_declaration:' + host, 'PASS' if value in (fixed, group) else 'FAIL',
                  'Domain-only live comparison; actual metadata still needs traffic: ' + str(value))
        relevant = set(policy['domain_suffixes'] + policy['exact_domains'] + policy['stun_hosts'] + [policy['intercom_host']])
        for connection in live['connections'].get('connections', []):
            meta = connection.get('metadata', {})
            host, process = meta.get('host', ''), meta.get('process', '')
            if not any(host == h or host.endswith('.' + h) for h in relevant):
                continue
            # Include Intercom only for Claude; unrelated browser Intercom is intentionally retained.
            if host == policy['intercom_host'] and process != policy['intercom_process']:
                continue
            chains = connection.get('chains', [])
            observed.append({'host': host, 'process': process, 'network': meta.get('network'),
                             'fixed_route': fixed in chains, 'bidirectional': connection.get('upload', 0) > 0 and connection.get('download', 0) > 0})
        for item in observed:
            check('observed_connection:' + item['host'], 'PASS' if item['fixed_route'] else 'FAIL', item)
    protected = []
    for path in [Path.home()/'.claude.json', Path.home()/'.claude/settings.json',
                 Path.home()/'.claude/settings.local.json', Path.home()/'.claude/CLAUDE.md',
                 Path.home()/'Library/Application Support/Claude/claude_desktop_config.json']:
        protected.append({'path': str(path), 'exists': path.is_file(),
                          'sha256': digest(path.read_bytes()) if path.is_file() else None})
    _, proposed = planned_rules(extension, runtime, policy)
    dns_checks, dns_report = audit_dns(root, runtime, policy, live)
    checks.extend(dns_checks)
    auxiliary_checks, auxiliary_report = audit_desktop_auxiliary(extension, runtime, policy, live)
    checks.extend(auxiliary_checks)
    return {'profile_uid': uid, 'rules_file': str(target), 'checks': checks,
            'configuration_status': 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'ATTENTION',
            'observed_connections': observed, 'protected_config_inventory': protected,
            'dns': dns_report,
            'desktop_auxiliary': auxiliary_report,
            'proposed_rules': proposed,
            'actual_exit_tests': 'PENDING: use real browser, desktop connections and separate STUN tests; static PASS is insufficient'}


def validate_candidate(path, root):
    executable = Path('/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo')
    if not executable.is_file():
        raise RuntimeError('Known Mihomo validator unavailable; no write performed')
    result = subprocess.run([str(executable), '-t', '-f', str(path), '-d', str(root)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if result.returncode:
        raise RuntimeError('Mihomo candidate validation failed; no write performed')


def repair(ctx, policy):
    root, uid, target, extension, runtime = ctx
    updated, rules = planned_rules(extension, runtime, policy)
    if updated == extension:
        return {'changed': False, 'reload_required': False, 'detail': 'Persistent rules already match; audit other findings separately'}
    node = next((p for p in runtime.get('proxies', []) if p.get('name') == policy['fixed_proxy']), None)
    group = next((g for g in runtime.get('proxy-groups', []) if g.get('name') == policy['claude_group']), None)
    if not node or node.get('server') != policy['proxy_server'] or node.get('port') != policy['proxy_port'] or not group:
        raise RuntimeError('Fixed endpoint or Claude group identity missing/changed; no rule write performed')
    backup_parent = Path.home()/'.local/state/mac-claude-network/backups'
    backup_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=backup_parent))
    os.chmod(backup, 0o700)
    files = sorted(set(root.glob('*.yaml')) | set((root/'profiles').glob('*.yaml')) | set((root/'profiles').glob('*.js')))
    manifest = {'config_directory': str(root), 'profile_uid': uid, 'files': {}}
    for source in files:
        if source.is_symlink():
            raise RuntimeError('Symlink encountered in configuration; no write performed')
        relative = source.relative_to(root)
        destination = backup/'original'/relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = source.read_bytes()
        private_write(destination, data)
        manifest['files'][str(relative)] = digest(data)
        if digest(destination.read_bytes()) != digest(data):
            raise RuntimeError('Backup verification failed; no write performed')
    selectors = live_state(root, runtime)
    manifest['selectors_before'] = {k:v['now'] for k,v in selectors['proxies'].get('proxies', {}).items() if v.get('now')} if selectors else None
    candidate = dict(runtime)
    identities = {rule_identity(r) for r in rules}
    candidate['rules'] = rules + [r for r in runtime.get('rules', []) if rule_identity(r) not in identities]
    candidate_path = backup/'candidate.yaml'
    private_write(candidate_path, yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False).encode())
    validate_candidate(candidate_path, root)
    before = target.read_bytes()
    if any(digest((root/relative).read_bytes()) != value for relative, value in manifest['files'].items()):
        raise RuntimeError('Concurrent configuration edit detected; no write performed')
    after = yaml.safe_dump(updated, allow_unicode=True, sort_keys=False).encode()
    manifest['rule_change'] = {'relative_path': str(target.relative_to(root)), 'before': digest(before), 'after': digest(after)}
    json_write(backup/'manifest.json', manifest)
    private_write(target, after)
    return {'changed': True, 'backup': str(backup), 'rules_file': str(target), 'rules_promoted': rules,
            'reload_required': True, 'detail': 'Reactivate the SAME profile via native Clash UI, then audit and test actual exits'}


def rollback(backup):
    backup = backup.expanduser().resolve()
    manifest = json.loads((backup/'manifest.json').read_text())
    root = Path(manifest['config_directory']).resolve()
    change = manifest['rule_change']
    relative = Path(change['relative_path'])
    if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'profiles':
        raise ValueError('invalid rollback target')
    target = root/relative
    original = backup/'original'/relative
    if target.is_symlink() or target.resolve().parent != (root/'profiles').resolve():
        raise ValueError('unsafe rollback path')
    if digest(target.read_bytes()) != change['after']:
        raise RuntimeError('Later edit detected; refusing whole-file rollback')
    data = original.read_bytes()
    if digest(data) != change['before']:
        raise RuntimeError('Backup hash mismatch; rollback refused')
    private_write(target, data)
    return {'restored': str(target), 'reload_required': True, 'detail': 'Reactivate the same profile and verify'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='audit', choices=['audit', 'repair', 'rollback'])
    parser.add_argument('--config-dir', type=Path)
    parser.add_argument('--policy', type=Path, default=SKILL/'references/baseline.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--compare', type=Path, help='Compare with an explicitly selected earlier audit report; no history is saved')
    args = parser.parse_args()
    if args.compare and args.mode != 'audit':
        parser.error('--compare is only available in audit mode')
    if args.compare and args.output and args.compare.expanduser().resolve() == args.output.expanduser().resolve():
        parser.error('Comparison input and output must be different files')
    try:
        started_at = utc_now()
        previous = json.loads(args.compare.expanduser().read_text()) if args.compare else None
        if args.compare and (not isinstance(previous, dict) or not isinstance(previous.get('checks'), list)):
            raise RuntimeError('Comparison input must be an audit report; no configuration was changed')
        policy = json.loads(args.policy.read_text())
        if args.mode == 'rollback':
            if not args.backup:
                raise ValueError('--backup required')
            result, code = rollback(args.backup), 0
        else:
            ctx = context(args.config_dir or Path(policy['config_directory']))
            if args.mode == 'audit':
                result = build_audit_report(ctx, policy, live_state(ctx[0], ctx[4]), args.policy, started_at)
                if args.compare:
                    result['report_comparison'] = compare_reports(previous, result)
                code = 0 if result['configuration_status'] == 'PASS' else 2
            else:
                result, code = repair(ctx, policy), 0
        if args.output:
            json_write(args.output.expanduser(), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except Exception as error:
        # Parser or controller errors can contain secrets. Never emit raw exception text.
        safe = str(error) if isinstance(error, RuntimeError) else 'Configuration read/structure error; inspect locally without exposing credentials'
        print(json.dumps({'error_type': type(error).__name__, 'error': safe}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
