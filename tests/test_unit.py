#!/usr/bin/env python3
"""Targeted no-network regressions for the Python port; standard library only."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import loggly

ENV = {'LOGGLY_API_TOKEN': 'private-api-token', 'LOGGLY_SUBDOMAIN': 'example',
       'LOGGLY_CUSTOMER_TOKEN': 'private-customer-token'}


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def rejected(self, command, *args):
        with self.assertRaises(loggly.Error) as caught:
            loggly.dry_run(command, *args)
        self.assertEqual(caught.exception.code, 2)

    def test_doctor_reports_validity_without_secrets(self):
        self.assertTrue(loggly.doctor()['ok'])
        text = json.dumps(loggly.doctor())
        self.assertNotIn('private', text)
        os.environ['LOGGLY_API_TOKEN'] = 'bad\ntoken'
        self.assertFalse(loggly.doctor()['ok'])
        self.assertFalse(loggly.doctor()['checks']['api_token'])
        os.environ['LOGGLY_API_TOKEN'] = ENV['LOGGLY_API_TOKEN']
        del os.environ['LOGGLY_CUSTOMER_TOKEN']
        self.assertTrue(loggly.doctor()['ok'])

    def test_dry_run_omits_values_and_reads_no_stdin(self):
        plan = loggly.dry_run('send', '-', 'app', 'application/json')
        self.assertEqual(plan['endpoint'], '/inputs/{customer_token}/')
        self.assertEqual(plan['body_source'], 'stdin')
        self.assertEqual(plan['authentication'], 'customer-token')
        self.assertNotIn('private', json.dumps(plan))
        plan = loggly.dry_run('request', 'POST', '/api/private-value?x=private-value')
        self.assertEqual(plan['endpoint'], '(same account path)')
        self.assertNotIn('private-value', json.dumps(plan))
        self.assertEqual(plan['query_keys'], [])
        next_plan = loggly.dry_run('next', '/apiv2/events/iterate?next=private-value')
        self.assertEqual(next_plan['endpoint'], '/apiv2/events/iterate?next=...')
        self.assertEqual(next_plan['query_keys'], [])
        class Unreadable:
            @property
            def buffer(self):
                raise AssertionError('dry-run read stdin')
        with patch.object(sys, 'stdin', Unreadable()), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loggly.main(['--dry-run','send','-','app','text/plain']), 0)
        self.assertEqual(json.loads(out.getvalue())['method'], 'POST')

    def test_tag_restrictions_match_vendor(self):
        for tag in ('~', '.app', '_app', '-app', 'a'*65, 'a,,b', 'a,', ',a'):
            self.rejected('send', '-', tag, 'text/plain')
        self.assertEqual(loggly.dry_run('send', '-', 'a'*64, 'text/plain')['method'], 'POST')
        self.assertEqual(loggly.dry_run('send', '-', '-', 'text/plain')['method'], 'POST')

    def test_known_query_validation_and_repeatable_lists(self):
        for args in [('q=a','q=b'), ('size=0',), ('size=1001',), ('size=2.5',), ('order=random',), ('q=',)]:
            self.rejected('iterate', *args)
        self.rejected('count', 'include_volume=1')
        self.rejected('usage', 'from=a','from=b','until=c')
        plan = loggly.dry_run('usage', 'from=a','until=b','group_by=host','group_by=app')
        self.assertEqual(plan['query_keys'], ['from','until','group_by','group_by'])
        self.assertEqual(loggly.dry_run('iterate','future=a','future=b')['query_keys'], ['future','future'])

    def test_generic_url_canonicalization_is_unambiguous(self):
        for path in ('//evil.invalid/a', '/a/../b', '/a/./b','/a/%2e%2e/b','/a/%5cb','/a/%0db', '/a/%zz'):
            self.rejected('request', 'GET', path)
        self.rejected('next', 'https://example.loggly.com.evil.invalid/apiv2/events/iterate?next=x')
        self.rejected('next', '/apiv2/events/iterate?')

    def test_structured_call_maps_types_body_and_repeatable_values(self):
        with patch.object(loggly, 'call', return_value=b'{}') as call:
            self.assertEqual(loggly.call_tool('count', {'q':'error','include_volume':True}), b'{}')
            call.assert_called_once_with('count','q=error','include_volume=true',body='',timeout=None)
        with patch.object(loggly, 'call', return_value=b'{}') as call:
            loggly.call_tool('usage', {'from':'a','until':'b','group_by':['host','app']})
            self.assertEqual(call.call_args.args, ('usage','from=a','until=b','group_by=host','group_by=app'))
        with patch.object(loggly, 'call', return_value=b'{}') as call:
            loggly.call_tool('send', {'body':'hello'})
            self.assertEqual(call.call_args.args, ('send','-','-','text/plain'))
            self.assertEqual(call.call_args.kwargs['body'], 'hello')
        for inputs in ({'bogus':'x'}, {'include_volume':'true'}, {'q':None}):
            with self.assertRaises(loggly.Error): loggly.call_tool('count', inputs)
        with self.assertRaises(loggly.Error):
            loggly.call_tool('request', {'method':'GET','path':'/api','body':''})

    def test_bounded_pagination_reports_incomplete_work(self):
        pages = [b'{"events":[],"next":"https://example.loggly.com/apiv2/events/iterate?next=x"}', b'{"events":[]}']
        with patch.object(loggly,'call',side_effect=pages) as call:
            self.assertEqual(len(list(loggly.iter_pages('q=error',max_pages=2))),2)
            self.assertEqual(call.call_args_list[1].args[0], 'next')
        with patch.object(loggly,'call',return_value=pages[0]):
            with self.assertRaisesRegex(loggly.Error,'max_pages'):
                list(loggly.iter_pages(max_pages=1))
            with self.assertRaisesRegex(loggly.Error,'repeated'):
                list(loggly.iter_pages(max_pages=5))
        with patch.object(loggly,'call',return_value=b'not json'):
            with self.assertRaisesRegex(loggly.Error,'invalid JSON'):
                list(loggly.iter_pages())

    def test_retry_hint_respects_side_effects(self):
        for command,args,allowed in [('count',(),True),('pixel',('-','message=x'),False),('request',('GET','/api'),False)]:
            req=loggly._prepare(command,args,os.environ)
            err=loggly._http_error(req,503,{'Retry-After':'30'})
            self.assertEqual(err.retryable,allowed)
            self.assertEqual(err.retry_after,30)
            self.assertNotIn('private',json.dumps(err.as_dict()))

    def test_new_discovery_is_offline_and_machine_readable(self):
        for argv in (['version'], ['--version'], ['doctor'], ['examples'], ['examples','count'],
                     ['skill','list'], ['skill','show','references/api.md'],
                     ['completion','bash'], ['completion','zsh'], ['completion','fish'], ['completion','nu']):
            with patch.object(loggly, '_transport', side_effect=AssertionError('discovery called HTTP')):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(loggly.main(argv), 0, argv)
                self.assertTrue(out.getvalue(), argv)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loggly.main(['skill','list']), 0)
        self.assertEqual(json.loads(out.getvalue()), loggly.skill_resources())
        for command in loggly.tools()['tools']:
            self.assertTrue(loggly.examples(command['name']))
        for shell in ('bash','zsh','fish','nu'):
            self.assertIn('loggly', loggly.completion(shell))

    def test_json_helper_has_no_silent_non_json_success(self):
        with patch.object(loggly,'call',return_value=b'{"count":5}'):
            self.assertEqual(loggly.call_json('count')['count'], 5)
        for invalid in (b'not json',b'{"count":NaN}',b'\xff'):
            with patch.object(loggly,'call',return_value=invalid):
                with self.assertRaises(loggly.Error): loggly.call_json('count')
        with patch.object(loggly,'call',side_effect=AssertionError('should reject before HTTP')):
            with self.assertRaises(loggly.Error): loggly.call_json('pixel','-')
            with self.assertRaises(loggly.Error): loggly.call_json('events','rsid=a','format=csv')

    def test_skill_resource_lookup_cannot_escape(self):
        for path in ('../README.md','/etc/passwd','references/../../README.md'):
            with self.assertRaises(loggly.Error): loggly.skill(path)
        self.assertTrue(loggly.skill().startswith('---'))


if __name__ == '__main__':
    unittest.main()
