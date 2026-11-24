#!/usr/bin/env python3
"""Development-only contract tests; require Python, jsonschema, openssl, and (Lua only) curl. No live Loggly requests."""
import json
import hashlib
import sys
import os
import re
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'loggly'
PYTHON = (ROOT / 'loggly.py').exists()
# Redirect only the fixture domains to the local TLS server, while preserving
# the original HTTPS hostname, SNI and certificate verification. The production
# Python transport contains no test-only endpoint override.
PYTHON_TEST_BOOTSTRAP = r"""
import os, socket, sys, runpy
real_connect = socket.create_connection
def connect(address, *args, **kwargs):
    if address[0] not in ('example.loggly.com', 'logs-01.loggly.com'):
        raise RuntimeError('test blocked external connection')
    return real_connect(('127.0.0.1', int(os.environ['TEST_PORT'])), *args, **kwargs)
socket.create_connection = connect
script = sys.argv.pop(1)
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name='__main__')
"""
def command(*args, env=None, script=CLI):
    if PYTHON and env and 'TEST_PORT' in env:
        return [sys.executable, '-c', PYTHON_TEST_BOOTSTRAP, str(script), *args]
    return [str(script), *args]


def call(*args, env=None, body=None):
    return subprocess.run(command(*args, env=env), env=env, input=body or b'', capture_output=True, check=True)

catalog = json.loads(call('tools').stdout)['tools']
by_name = {item['name']: item for item in catalog}
canonical = ROOT.parent / 'spec' / 'catalog.json'
if canonical.exists():
    assert {'tools': catalog} == json.loads(canonical.read_text()), 'canonical catalog parity'
assert len(catalog) == len(by_name) == 15
assert set(by_name) == {'search','events','iterate','next','count','fields','field','stats','usage','customer','users','send','bulk','pixel','request'}
for name, tool in by_name.items():
    assert json.loads(call('schema', name).stdout) == tool
    assert tool['description'].encode() in call('help', name).stdout
    for schema_name in ['inputSchema','outputSchema']:
        Draft202012Validator.check_schema(tool[schema_name])
    cli = tool['x-cli']
    props = tool['inputSchema']['properties']
    assert cli['argv'][:2] == ['loggly', name]
    assert set(cli['queryParameters']) <= props.keys()
    assert all(arg['property'] in props for arg in cli['argv'] if isinstance(arg, dict))
    for key in ['stdinProperty','queryObject']:
        assert cli.get(key) is None or cli[key] in props
    assert {'LOGGLY_API_TOKEN','LOGGLY_SUBDOMAIN'} <= set(cli['environment'])

# Keep repository and embedded skill synchronized and all relative resources valid.
skill_root = ROOT / 'skills' / 'loggly'
skill_file = skill_root / 'SKILL.md'
skill = skill_file.read_text()
assert call('skill', 'show').stdout == skill_file.read_bytes()
with tempfile.TemporaryDirectory() as isolated:
    standalone = Path(isolated)
    for filename in ('loggly', 'loggly.py' if PYTHON else 'loggly.lua'):
        shutil.copy2(ROOT / filename, standalone / filename)
    bin_dir = standalone / 'bin'; bin_dir.mkdir()
    interpreter = 'python3' if PYTHON else 'lua'
    (bin_dir / interpreter).symlink_to(shutil.which(interpreter))
    result = subprocess.run([str(standalone / 'loggly'), 'skill', 'show'],
                            cwd=isolated, env={'PATH': str(bin_dir)},
                            capture_output=True, check=True)
    assert result.stdout == skill_file.read_bytes()
frontmatter = skill.split('---\n', 2)[1]
assert re.search(r'^name: loggly$', frontmatter, re.M)
description = re.search(r'^description: (.+)$', frontmatter, re.M)
assert description and 0 < len(description.group(1)) <= 1024
compatibility = re.search(r'^compatibility: (.+)$', frontmatter, re.M)
assert compatibility is None or len(compatibility.group(1)) <= 500
assert len(skill.splitlines()) < 500
for target in re.findall(r'\]\(([^)]+)\)', skill):
    assert (skill_root / target).is_file(), target
example_commands = set()
for page in sorted(skill_root.glob('examples/*.md')) + [skill_file] + sorted(skill_root.glob('references/*.md')):
    for snippet in re.findall(r'^```sh\n(.*?)^```$', page.read_text(), re.M | re.S):
        subprocess.run(['sh', '-n'], input=snippet.encode(), check=True)
        if page.parent.name == 'examples':
            example_commands.update(re.findall(r'\bloggly ([a-z]+)\b', snippet))
assert set(by_name) <= example_commands, set(by_name) - example_commands

def invocation(tool, inputs):
    """Reference implementation of x-cli mapping, not a runtime dependency."""
    Draft202012Validator(tool['inputSchema']).validate(inputs)
    cli = tool['x-cli']
    argv = []
    for arg in cli['argv'][1:]:
        if isinstance(arg, str):
            argv.append(arg)
            continue
        value = inputs.get(arg['property'], arg.get('default'))
        if value is None and arg.get('omitIfAbsent'):
            continue
        assert value is not None
        if 'flag' in arg:
            argv.append(arg['flag'])
        argv.append(str(value))
    query = {k: inputs[k] for k in cli['queryParameters'] if k in inputs}
    query.update(inputs.get(cli.get('queryObject'), {}))
    for key, values in query.items():
        for val in values if isinstance(values, list) else [values]:
            if isinstance(val, bool): val = str(val).lower()
            argv.append(f'{key}={val}')
    body = inputs.get(cli['stdinProperty'], '').encode() if cli['stdinProperty'] else b''
    return argv, body

# A local TLS endpoint captures the actual request made by curl (including the
# content type, encoding, credentials and exact payload). No live endpoints.
seen = []
fixtures = {
    '/apiv2/search': {'rsid':{'id':'42'}},
    '/apiv2/events': {'events':[], 'page':0, 'total_events':0},
    '/apiv2/events/iterate': {'events':[], 'next':'https://example.loggly.com/apiv2/events/iterate?next=xyz'},
    '/apiv2/events/count': {'count':5,'volume':100},
    '/apiv2/fields/': {'fields':[{'name':'json.duration'}]},
    '/apiv2/fields/json.a%20b/': {'json.a b':[{'term':'x','count':5}],'total_events':5},
    '/apiv2/stats/avg/json.duration': {'field':'json.duration','stats':{'avg':1.2}},
    '/apiv2/volume-metrics': [{'count':5,'startTimestamp':'1','endTimestamp':'2','host':'a'}],
    '/apiv2/customer': {'subdomain':'example','tokens':['fixture-only'],'subscription':{'retention_days':7,'volume_limit_mb':100}},
    '/apiv2/user-list': {'message':'success','users':[]},
}
class Server(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def serve(self):
        parsed = urlsplit(self.path)
        body = self.rfile.read(int(self.headers.get('Content-Length',0)))
        seen.append((self.command, parsed.path, parse_qs(parsed.query,keep_blank_values=True), dict(self.headers), body))
        if parsed.path == '/apiv2/error':
            status, data, mime = 401, b'error', 'text/plain'
        elif parsed.path == '/apiv2/redirect':
            status, data, mime = 302, b'redirect', 'text/plain'
        elif parsed.path.endswith('.gif'):
            status, data, mime = 200, b'GIF89a\x00\x01', 'image/gif'
        else:
            status, mime = 200, 'application/json'
            data = json.dumps(fixtures.get(parsed.path, {'response':'ok'})).encode()
        self.send_response(status)
        if status == 302: self.send_header('Location','https://evil.invalid/')
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(data)
    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = serve

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=example.loggly.com','-addext','subjectAltName=DNS:example.loggly.com,DNS:logs-01.loggly.com','-keyout',str(p/'key.pem'),'-out',str(p/'cert.pem')], check=True, capture_output=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(p/'cert.pem',p/'key.pem')
    server = ThreadingHTTPServer(('127.0.0.1',0),Server)
    server.socket = ctx.wrap_socket(server.socket,server_side=True)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        shim = p/'curl'
        shim.write_text('''#!/bin/sh
# Refuse credentials in curl process arguments or environment.
for arg do case $arg in *fixture-api-token*|*fixture-customer-token*) exit 97;; esac; done
[ -z "${LOGGLY_API_TOKEN:-}" ] && [ -z "${LOGGLY_CUSTOMER_TOKEN:-}" ] || exit 98
exec "$REAL_CURL" -q --noproxy '*' --cacert "$TEST_CERT" --connect-to "example.loggly.com:443:127.0.0.1:$TEST_PORT" --connect-to "logs-01.loggly.com:443:127.0.0.1:$TEST_PORT" "$@"
''')
        shim.chmod(0o755)
        env = dict(os.environ, PATH=f'{p}:{os.environ["PATH"]}',REAL_CURL=shutil.which('curl') or '',TEST_CERT=str(p/'cert.pem'),TEST_PORT=str(server.server_port),LOGGLY_API_TOKEN='fixture-api-token',LOGGLY_CUSTOMER_TOKEN='fixture-customer-token',LOGGLY_SUBDOMAIN='example',SSL_CERT_FILE=str(p/'cert.pem'))
        env = {k: v for k,v in env.items() if not k.lower().endswith('_proxy')}
        if PYTHON:
            env['PATH'] = '/nonexistent'  # proves no curl dependency on API calls

        examples = {
            'search':{'q':'x & y=é'},'events':{'rsid':'42'},'iterate':{'q':'error','size':2},
            'next':{'url':fixtures['/apiv2/events/iterate']['next']},'count':{'include_volume':True},
            'fields':{},'field':{'field':'json.a b'},'stats':{'type':'avg','field':'json.duration'},
            'usage':{'from':'-1h','until':'now','group_by':['host','app']},'customer':{},'users':{},
            'send':{'tags':'app,web','body':'x\n\x00y'},'bulk':{'body':'a\nb\n'},
            'pixel':{'tags':'app,web','query':{'message':'hello world','PLAINTEXT':'{"x":1}'}},
            'request':{'method':'POST','path':'/apiv2/custom?x=a%20b','body':'{"test":true}'},
        }
        for name, inputs in examples.items():
            tool = by_name[name]
            argv, body = invocation(tool,inputs)
            res = call(*argv,env=env,body=body)
            method,path,query,headers,actual_body = seen[-1]
            if name in {'send','bulk','pixel'}:
                assert 'Authorization' not in headers
                assert 'fixture-customer-token' in path
            else:
                assert headers['Authorization'] == 'bearer fixture-api-token'
            if name == 'pixel': assert res.stdout == b'GIF89a\x00\x01'
            else: Draft202012Validator(tool['outputSchema']).validate(json.loads(res.stdout))
            if name == 'search': assert query['q'] == ['x & y=é']
            if name == 'count': assert query['include_volume'] == ['true']
            if name == 'usage': assert query['group_by'] == ['host','app']
            if name == 'send': assert {k.lower():v for k,v in headers.items()}['x-loggly-tag'] == 'app,web'
            if name in {'send','bulk','request'}: assert actual_body == body and method == 'POST'
            if name == 'request': assert query['x'] == ['a b']
        result=call('request','HEAD','/apiv2/customer','x=a b',env=env)
        assert seen[-1][0] == 'HEAD' and seen[-1][2]['x']==['a b'] and result.stdout.startswith(b'HTTP/')
        res=subprocess.run(command('request','GET','/apiv2/error',env=env),env=env,capture_output=True)
        assert res.returncode == 22
        before=len(seen)
        redirect = subprocess.run(command('request','GET','/apiv2/redirect',env=env),env=env,capture_output=True)
        assert redirect.returncode == 22 and redirect.stdout == b'' and len(seen) == before + 1
        for stat in 'avg sum min max percentiles value_count cardinality stats all extended'.split():
            call('stats',stat,'json.duration',env=env)
            assert seen[-1][1] == f'/apiv2/stats/{stat}/json.duration'
        call('field','json.café/a%',env=env)
        assert seen[-1][1] == '/apiv2/fields/json.caf%C3%A9%2Fa%25/'
        query = 'a"\\b\nheader = "evil"\t & é'
        call('iterate','q='+query,'size=2',env=env)
        assert seen[-1][2]['q'] == [query]
        call('pixel','-','--tags','app,web','message=hi',env=env)
        assert seen[-1][1] == '/inputs/fixture-customer-token/tag/app/web/1*1.gif'
        call('next','/apiv2/events/iterate?next=xyz',env=env)
        assert seen[-1][2]['next'] == ['xyz']
        call('send','-','-','text/plain',env=env,body=b'\x00\xff\r\n')
        assert seen[-1][4] == b'\x00\xff\r\n'
        for method in ('PUT','PATCH','DELETE'):
            call('request',method,'/apiv2/example',env=env,body=b'{}' if method != 'DELETE' else b'')
            assert seen[-1][0] == method
        invalid = [('next','https://evil.example/apiv2/events/iterate?next=cursor'),
                   ('next','https://example.loggly.com.evil.example/apiv2/events/iterate?next=cursor'),
                   ('next','/apiv2/events/iterate?next=x#fragment'),
                   ('request','GET','//evil.example/path'),('request','GET','https://evil.example/path'),
                   ('request','GET','/apiv2/"bad'),('request','GET','/apiv2/\\bad'),
                   ('request','GET','/apiv2/a b'),('request','GET','/apiv2/a#bad'),
                   ('request','GET','/apiv2/a\nheader = evil'),('search',),('search','q='),('events',),
                   ('usage','from=-1h'),('usage','until=now'),('search','q=test','--insecure'),
                   ('search','q=test','=value'),('search','q=test','a@/etc/passwd=value'),
                   ('customer','extra=1'),('request','POST','/apiv2/example','q=x'),('field','..'),
                   ('stats','unknown','foo'),('send','-','a,,b','text/plain'),
                   ('send','-','a/../b','text/plain'),('send','-','app','text/plain; bad'),('pixel','-','--tags')]
        before = len(seen)
        for args in invalid:
            result = subprocess.run(command(*args,env=env),env=env,input=b'',capture_output=True)
            assert result.returncode == 2, (args,result.returncode,result.stderr)
        for key,value in [('LOGGLY_API_TOKEN',''),('LOGGLY_SUBDOMAIN',''),('LOGGLY_API_TOKEN','bad"token'),('LOGGLY_SUBDOMAIN','example.evil'),('LOGGLY_CUSTOMER_TOKEN','')]:
            invalid_env = dict(env,**{key:value})
            args = ('pixel','-','message=x') if key == 'LOGGLY_CUSTOMER_TOKEN' else ('count',)
            result = subprocess.run(command(*args,env=invalid_env),env=invalid_env,capture_output=True)
            assert result.returncode == 2
        assert len(seen) == before
        # Exercise the actual imported SDK, not just its CLI.
        if PYTHON:
            native = p/'native.py'
            native.write_text('import sys; sys.path.insert(0, '+repr(str(ROOT))+'); import loggly; import json; assert json.loads(loggly.call("count", "q=error"))["count"] == 5; assert len(loggly.tools()["tools"]) == 15')
            subprocess.run(command(env=env,script=native),env=env,check=True)
        else:
            native = p/'native.lua'
            native.write_text('local sdk=assert(loadfile('+json.dumps(str(ROOT/'loggly.lua'))+'))(); local data, code, msg=sdk.call("count", {"q=error"}); assert(code == 0 and data:find("5"), msg); local gif, status = sdk.call("pixel", {"-", "message=x"}); assert(status == 0 and gif == "GIF89a\\0\\1"); local d, c = sdk.call("search", {}); assert(d == nil and c == 2)')
            subprocess.run(['lua',str(native)],env=env,check=True)
        # Invalid certificate must fail without leaking credentials.
        bad_env = dict(env, SSL_CERT_FILE='/nonexistent', TEST_CERT='/nonexistent')
        result = subprocess.run(command('count',env=bad_env),env=bad_env,capture_output=True)
        assert result.returncode != 0 and b'fixture-api-token' not in result.stderr
    finally:
        server.shutdown();server.server_close();thread.join()
print('PASS: skill metadata, offline standalone output, resource links, example syntax and coverage')
print('PASS: 15 input/output schemas, CLI routing, imported API, TLS, binary payloads, validation and redirect rejection')
